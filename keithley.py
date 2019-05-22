#!/usr/bin/env python

import logging
import visa
import time
import useserial
import numpy as np

class KeithleyMeter ( object ) :
	def __init__ ( self, resource_name ) :
		logger = logging.getLogger ( u'myLogger' )
		resources = [""] * 1
		try :
			rm1 = visa.ResourceManager ( )
			resources = rm1.list_resources ( )
		except :
			logger.debug ( u"  Failed to open ni-visa" )
		try :
			if useserial.haveserial :
				rm2 = visa.ResourceManager ( '@py' )
				resources += rm2.list_resources ( )
		except :
			logger.debug ( u"  Failed to open py-visa" )
		if not resource_name in resources :
			self._connected = False
			raise ValueError ( "Resource not found {}" .format ( resource_name ) )
		if resource_name.startswith ( "ASRL" ) and useserial.haveserial :
			logger.debug ( u"  Opening {} with py-visa." .format ( resource_name ) )
			# 5000 msecs needed to catch slow devices...
			self._res = rm2.open_resource ( resource_name, baud_rate = 19200, data_bits = 8, timeout = 5000 )
		else :
			logger.debug ( u"  Opening {} with ni-visa." .format ( resource_name ) )
			self._res = rm1.open_resource ( resource_name )
		self._connected = True

		self._write ( "*RST" )

	def identify ( self ) :
		return self._query ( "*IDN?" ) .strip ( )

	def get_reading ( self ) :
		return self._query ( "READ?" ) .strip ( )

	def _write ( self, cmd ) :
		self._res.write ( cmd )

	def _query ( self, cmd ) :
		return self._res.query ( cmd )

	def _query_ascii_values ( self, cmd ) :
		return self._res.query_ascii_values ( cmd )

	def _read ( self ) :
		return self._res.read ( )

class Keithley6517B ( KeithleyMeter ) :
	def __init__ ( self, resource_name ) :
		super ( Keithley6517B, self ) .__init__ ( resource_name )

		self._write ( ":SYSTEM:ZCHECK OFF" )

		self._write ( ":OUTPUT1:STATE OFF" )
		self._write ( ":SOURCE:VOLTAGE:RANGE 100" )
		self._1000_range = False

		self._write ( ":SENSE:FUNCTION 'CURRENT:DC'" )

		self._write ( ":SENSE:CURRENT:DC:NPLCYCLES 100; AVERAGE:COUNT 5; STATE OFF" )
		self._write ( ":FORMAT:ELEMENTS READING,UNITS,VSOURCE" )

	# FIXME
	def set_compliance ( self, compliance ) :
		#self._write ( ":SENSE:CURRENT:PROT {}" .format ( compliance ) )
		print ( u"Hardware compliance not implemented yet!" )

	def voltage_series ( self, start_volt, end_volt, absstep_volt ) :
		if self.get_source_voltage ( ) != 0 :
			self.set_source_voltage ( 0 )
		self.set_output_state ( True )

		if end_volt < start_volt:
			step_mvolt = int ( -abs ( absstep_volt ) * 1000 )
		else:
			step_mvolt = int ( abs ( absstep_volt ) * 1000 )
		start_mvolt = int ( start_volt * 1000 )
		end_mvolt = int ( end_volt * 1000 ) + ( step_mvolt // abs ( step_mvolt ) )

		for mvolt in range ( start_mvolt, end_mvolt, step_mvolt ) :
			self.set_source_voltage_cont ( mvolt / 1000 )
			yield self.get_source_voltage ( )

	def stop_measurement ( self ) :
		self.set_source_voltage_cont ( 0 )
		self.set_output_state ( False )

	def set_1000_range ( self, state ) :
		if not state :
			self._write ( ":SOURCE:VOLTAGE:RANGE 100" )
			self._1000_range = False
		else:
			self._write( ":SOURCE:VOLTAGE:RANGE 1000" )
			self._1000_range = True

	def is_1000_range ( self ) :
		return self._1000_range

	def get_source_voltage ( self ) :
		return self._query_ascii_values ( ":SOURCE:VOLTAGE?" ) [0]

	def set_source_voltage ( self, volts ) :
		logger = logging.getLogger ( u'myLogger' )
		if not -1000 <= volts <= 1000 :
			raise ValueError ( "Voltage level out of range [-1000;1000]: {}" .format ( volts ) )

		if abs ( volts ) > 100 and not self.is_1000_range ( ) :
			self.set_1000_range ( True )
		elif abs ( volts ) < 100 and self.is_1000_range ( ) :
			self.set_1000_range ( False )

		logger.debug ( u"Setting source voltage to {:.2f} V" .format ( volts ) )
		self._write ( ":SOURCE:VOLTAGE {}" .format ( volts ) )

	def set_output_state ( self, state ) :
		if state :
			self._write ( ":OUTPUT1:STATE ON" )
		else :
			self._write ( ":OUTPUT1:STATE OFF" )

	def set_source_voltage_cont ( self, target, speed = 100 ) :
		interval = 0.1
		step = interval * speed
		U = self.get_source_voltage ( )
		while abs ( U - target ) > abs ( step ) :
			if U < target :
				U = min ( U + step, target )
			else :
				U = max ( U - step, target )
			self.set_source_voltage ( U )
			time.sleep ( interval / 2 )
			U = self.get_source_voltage ( )
			time.sleep ( interval / 2 )
		self.set_source_voltage ( target )

	def parse_iv ( self, line, devname ) :
		voltage = current = None
		print ( u"read %s", line )
		for field in line.split ( "," ) :
			if field[-3:] == "ADC" :
				current = float ( field[:-3] )
			elif field[-1:] == "A" :
				current = float ( field[:-1] )
			elif field[-4:] == "Vsrc" :
				voltage = float ( field[:-4] )
		return { "{}_srcvoltage".format ( devname ) : voltage, "{}_current" .format ( devname ) : current }

class Keithley2410 ( KeithleyMeter ) :
	def __init__ ( self, resource_name ) :
		super ( Keithley2410, self ) .__init__ ( resource_name )

		self._write ( ":OUTPUT1:STATE OFF" )
		self._write ( ":SOURCE:VOLTAGE:RANGE 100" )
		self._1000_range = False

		self._write ( ":SENSE:FUNCTION 'CURRENT:DC'" )
		# only 6517b
		#self._write ( ":SENSE:CURRENT:DC:NPLCYCLES 1; AVERAGE:COUNT 5; STATE ON" )
		#self._write ( ":FORMAT:ELEMENTS READING,UNITS,VSOURCE" )
		
		#self._write(":SOUR:FUNC VOLT")
		#self._write(":SOUR:VOLT:MODE FIXED")
		#self._write(":SOUR:VOLT:RANG:AUTO ON")
		#print ("Setting Read Current mode")
		#self._write(":SENS:FUNC \"CURR\"")
		#self._write(":SENS:CURR:RANG:AUTO ON")
		###
		#print ("Setting current compliance to ", inst_current, " uA")
		
		#print ("Setting initial voltage to 0")
		#self._write(":SOUR:VOLT:LEV 0")

	def set_compliance ( self, compliance ) :
		self._write ( ":SENSE:CURRENT:PROT {}" .format ( compliance ) )

	def voltage_series ( self, start_volt, end_volt, absstep_volt ) :
		if self.get_source_voltage ( ) != 0 :
			self.set_source_voltage ( 0 )
		self.set_output_state ( True )

		if end_volt < start_volt:
			step_mvolt = int ( -abs ( absstep_volt ) * 1000 )
		else:
			step_mvolt = int ( abs ( absstep_volt ) * 1000 )
		start_mvolt = int ( start_volt * 1000 )
		end_mvolt = int ( end_volt * 1000 ) + ( step_mvolt // abs ( step_mvolt ) )

		for mvolt in range ( start_mvolt, end_mvolt, step_mvolt ) :
			self.set_source_voltage_cont ( mvolt / 1000 )
			yield self.get_source_voltage ( )

	def stop_measurement ( self ) :
		self.set_source_voltage_cont ( 0 )
		self.set_output_state ( False )

	def set_1000_range ( self, state ) :
		if not state :
			self._write ( ":SOURCE:VOLTAGE:RANGE 100" )
			self._1000_range = False
		else:
			self._write ( ":SOURCE:VOLTAGE:RANGE 1000" )
			self._1000_range = True

	def is_1000_range ( self ) :
		return self._1000_range

	def get_source_voltage ( self ) :
		return self._query_ascii_values ( ":SOURCE:VOLTAGE?" ) [0]

	def set_source_voltage ( self, volts ) :
		logger = logging.getLogger ( u'myLogger' )
		if not -1000 <= volts <= 1000 :
			raise ValueError ( "Voltage level out of range [-1000;1000]: {}" .format ( volts ) )

		if abs ( volts ) > 100 and not self.is_1000_range ( ) :
			self.set_1000_range ( True )
		elif abs ( volts ) < 100 and self.is_1000_range ( ) :
			self.set_1000_range ( False )

		logger.debug ( u"Setting source voltage to {:.2f} V" .format ( volts ) )
		self._write ( "SOUR:VOLT:LEV {}" .format ( volts ) )

	def set_output_state ( self, state ) :
		if state :
			self._write ( ":OUTPUT1:STATE ON" )
		else :
			self._write ( ":OUTPUT1:STATE OFF" )

	def set_source_voltage_cont ( self, target, speed = 100 ) :
		interval = 0.1
		step = interval * speed
		U = self.get_source_voltage ( )
		while abs ( U - target ) > abs ( step ) :
			if U < target :
				U = min ( U + step, target )
			else :
				U = max ( U - step, target )
			self.set_source_voltage ( U )
			time.sleep ( interval / 2 )
			U = self.get_source_voltage ( )
			time.sleep ( interval / 2 )
		self.set_source_voltage ( target )

	def parse_iv ( self, line, devname ) :
		voltage = current = None
		voltage = float(line.split(",",2)[0])
		current = float(line.split(",",2)[1])
		return { "{}_srcvoltage".format ( devname ) : voltage, "{}_current" .format ( devname ) : current }

class Keithley6482 ( KeithleyMeter ) :
	def __init__ ( self, resource_name ) :
		super ( Keithley6482, self ) .__init__ ( resource_name )

		self._write ( ":SENSE:FUNCTION 'CURRENT:DC'" )
		self._write ( ":FORMAT:ELEMENTS READING,UNITS" )
		self._write ( ":SENSE:AVERAGE:COUNT 5; STATE ON" )
		
	def parse_iv ( self, line, devname ) :
		voltage = current = None
		current = float(line.split(",",2)[0])
		voltage= float(line.split(",",2)[1])
		return { "{}_srcvoltage".format ( devname ) : voltage, "{}_current" .format ( devname ) : current }

if __name__ == "__main__" :
	k = Keithley6517B ( "GPIB0::21::INSTR" )
	l = Keithley6482 ( "GPIB0::11::INSTR" )
