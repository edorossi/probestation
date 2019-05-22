#!/usr/bin/env python

from __future__ import with_statement
from __future__ import division
from __future__ import absolute_import
import logging
from measurement_window import MeasurementThread, MeasurementWindow
import keithley
import agilent
import sys

try:
    from PyQt5 import QtWidgets as QtW
    from PyQt5 import QtCore
except ImportError as e :
    from PyQt4 import QtGui as QtW
    from PyQt4 import QtCore

import os
import csv
import datetime
from time import sleep
from pyvisa.errors import VisaIOError, InvalidBinaryFormat
from io import open
from collections import OrderedDict

def getDateTimeFilename ( ) :
	s = datetime.datetime.now ( ) .isoformat ( )
	s = s.replace ( u":", u"_" )
	s = s.replace ( u".", u"_" )
	return s

class CvMeasurementThread ( MeasurementThread ) :
	def __init__ ( self, args ) :
		super ( CvMeasurementThread, self ) .__init__ ( args )

	def run ( self ) :
		args = self.args

		fname = getDateTimeFilename ( )
		output_csv = os.path.join ( str ( args.output_dir ), fname + u".csv" )
		logger = logging.getLogger ( u'myLogger' )
		logger.debug ( u" In cv_measurement.py:" )

		try :
			input_hv = keithley.KeithleyMeter ( args.devname_hv )
			if input_hv.identify ( ) .startswith ( u"KEITHLEY INSTRUMENTS INC.,MODEL 6517B" ) :
				keith_hv = keithley.Keithley6517B ( args.devname_hv )
			elif input_hv.identify ( ) .startswith ( u"KEITHLEY INSTRUMENTS INC.,MODEL 2410" ) :
				keith_hv = keithley.Keithley2410 ( args.devname_hv )
			else :
				errormsg = u"Could not open devices."
				self.error_signal.emit ( errormsg )
				logger.error ( errormsg )
				self.finished.emit ( os.path.join ( str ( args.output_dir ), fname ) )
				return
			logger.info ( u"  Voltage source device introduced itself as {}" .format ( keith_hv.identify ( ) ) )
			agilentE4980A = agilent.AgilentE4980A ( args.devname_agiE4980A )
			logger.info ( u"LCR meter introduced itself as {}" .format ( agilentE4980A.identify ( ) ) )
		except VisaIOError :
			errormsg = u"Could not open devices."
			self.error_signal.emit ( errormsg )
			logger.error ( errormsg )
			self.finished.emit ( os.path.join ( str ( args.output_dir ), fname ) )
			return

		try :
			logger.info ( u"Starting measurement" )

			agilentE4980A.set_frequency ( args.frequency )
			agilentE4980A.set_voltage_level ( args.deltavolt )

			mode = 'w'
			if sys.version_info.major < 3:
				mode += 'b'

			keith_hv.set_compliance ( args.compcurrent )

			with open ( output_csv, mode ) as f :
				header = OrderedDict ( [ ( 'keihv_srcvoltage', None ), ( 'agie4980a_capacitance', None ), ('agie4980a_conductance', None ), ( 'keihv_current', None ) ] )
				writer = csv.DictWriter ( f, fieldnames = header, extrasaction = u"ignore" )
				writer.writeheader ( )

				for keivolt in keith_hv.voltage_series ( args.start, args.end, args.step ) :
					sleep ( args.sleep )
					if self._exiting :
						break

					line = agilentE4980A.get_reading ( )
					meas = agilent.parse_cgv ( line, u"agie4980a" )
					meas[u"keihv_srcvoltage"] = keivolt
					if ( not u"keihv_srcvoltage" in meas or not u"agie4980a_capacitance" in meas or not u"agie4980a_conductance" in meas or meas[u"keihv_srcvoltage"] is None or meas[u"agie4980a_capacitance"] is None or meas[u"agie4980a_conductance"] is None ) :
						raise IOError ( u"Got invalid reading from device" )
					compline = keith_hv.get_reading ( )
					meas.update ( keith_hv.parse_iv ( compline, u"keihv" ) )

					print ( u"VSrc = {: 10.4g} V; C = {: 10.4g} F; G = {: 10.4g} S; I = {: 10.4g} A" .format ( meas[u"keihv_srcvoltage"], meas[u"agie4980a_capacitance"], meas[u"agie4980a_conductance"], meas[u"keihv_current"] ) )

					if ( abs ( meas[u"keihv_current"] ) >= args.compcurrent ) :
						self.error_signal.emit ( u"Compliance current reached" )
						print ( u"Compliance current reached" )
						#Instant turn off
						keith_hv.set_output_state ( False )
						self._exiting = True

					writer.writerow ( meas )
					self.measurement_ready.emit ( ( meas[u"keihv_srcvoltage"], 1 / meas[u"agie4980a_capacitance"] ** 2 ) )

					if self._exiting :
						break
					sleep ( 2 )

		except IOError as e :
			errormsg = u"Error: {}" .format ( e )
			self.error_signal.emit ( errormsg )
			logger.error ( errormsg )


		except ( VisaIOError, InvalidBinaryFormat, ValueError ) :
			errormsg = u"Error during communication with devices."
			self.error_signal.emit ( errormsg )
			logger.error ( errormsg )
		finally :
			logger.info ( u"Stopping measurement" )
			try :
				keith_hv.stop_measurement ( )
			except ( VisaIOError, InvalidBinaryFormat, ValueError ) :
				logger.error ( u"Error during stopping. Trying to turn off output" )
				keith_hv.set_output_state ( False )

		self.finished.emit ( os.path.join ( str ( args.output_dir ), fname ) )

class CvMeasurementWindow ( MeasurementWindow ) :
	def __init__ ( self, parent, args ) :
		thread = CvMeasurementThread ( args )
		super ( CvMeasurementWindow, self ) .__init__ ( parent, 1, args, thread )

		self._ylabel = [u"Capacitance${}^{-2}$ in $\\mathrm{F}^{-2}$", u"Conductance in $\\mathrm{S}$"]
		self.setWindowTitle ( u"CV measurement" )
