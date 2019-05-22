#!/usr/bin/env python

from __future__ import with_statement
from __future__ import division
from __future__ import absolute_import
import logging
from measurement_window import MeasurementThread, MeasurementWindow
import keithley
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

class IvMeasurementThread ( MeasurementThread ) :
	def __init__ ( self, args ) :
		super ( IvMeasurementThread, self ) .__init__ ( args )

	def run ( self ) :
		args = self.args

		fname = getDateTimeFilename ( )
		output_csv = os.path.join ( str ( args.output_dir ), fname + u".csv" )
		logger = logging.getLogger ( u'myLogger' )
		logger.debug ( u" In iv_measurement.py:" )

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
			
			if not args.devname_kei6482 is None and args.guardring :
				keith6482 = keithley.Keithley6482 ( args.devname_kei6482 )
				logger.info ( u"  Guard ring device introduced itself as {}" .format ( keith6482.identify ( ) ) )
			else :
				keith6482 = None
				logger.info ( u"  Running without guard ring measurement" )
		except VisaIOError :
			errormsg = u"Could not open devices."
			self.error_signal.emit ( errormsg )
			logger.error ( errormsg )
			self.finished.emit ( os.path.join ( str ( args.output_dir ), fname ) )
			return

		try :
			logger.info ( u"Starting measurement" )
			mode = 'w'
			if sys.version_info.major < 3:
				mode += 'b'

			keith_hv.set_compliance ( args.compcurrent )

			with open ( output_csv, mode ) as f :
				if not keith6482 is None :
					header = OrderedDict ( [ ( 'keihv_srcvoltage', None ), ( 'keihv_current', None ), ( 'kei6482_current', None ) ] )
				else :
					header = OrderedDict ( [ ( 'keihv_srcvoltage', None ), ( 'keihv_current', None ) ] )
				writer = csv.DictWriter ( f, fieldnames = header, extrasaction = u"ignore" )
				writer.writeheader ( )

				for voltage in keith_hv.voltage_series ( args.start, args.end, args.step ) :
					sleep ( args.sleep )
					if self._exiting :
						break

					line = keith_hv.get_reading ( )
					meas = keith_hv.parse_iv ( line, u"keihv" )
					if ( not u"keihv_srcvoltage" in meas or not u"keihv_current" in meas or meas[u"keihv_srcvoltage"] is None or meas[u"keihv_current"] is None ) :
						raise IOError ( u"Got invalid response from Keithley 6517B" )
					if self._exiting :
						break

					if not keith6482 is None :
						gr_line = keith6482.get_reading ( )
						meas.update ( keith6482.parse_iv ( gr_line, u"kei6482" ) )
						if ( not u"kei6482_current" in meas or meas[u"kei6482_current"] is None ) :
							raise IOError ( u"Got invalid response from Keithley 6482" )
						print ( u"VSrc = {: 10.4g} V; I = {: 10.4g} A; IGr = {: 10.4g} A" .format ( meas[u"keihv_srcvoltage"], meas[u"keihv_current"], meas[u"kei6482_current"] ) )
					else :
						meas[u"kei6482_current"] = 0
						print ( u"VSrc = {: 10.4g} V; I = {: 10.4g} A" .format ( meas[u"keihv_srcvoltage"], meas[u"keihv_current"] ) )

					if ( abs ( meas[u"keihv_current"] ) >= args.compcurrent or abs ( meas[u"kei6482_current"] ) >= args.compcurrent ) :
						self.error_signal.emit ( u"Compliance current reached" )
						print ( u"Compliance current reached" )
						#Instant turn off
						keith_hv.set_output_state ( False )
						self._exiting = True

					writer.writerow ( meas )
					if args.guardring :
						self.measurement_ready.emit ( ( meas[u"keihv_srcvoltage"], meas[u"keihv_current"], meas[u"kei6482_current"] ) )
					else :
						self.measurement_ready.emit ( ( meas[u"keihv_srcvoltage"], meas[u"keihv_current"] ) )
					if self._exiting :
						break

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
				logger.error ( u"Error during stopping. Trying turn off output" )
				keith_hv.set_output_state ( False )

		self.finished.emit ( os.path.join (  str ( args.output_dir ), fname ) )

class IvMeasurementWindow ( MeasurementWindow ) :
	def __init__ ( self, parent, args ) :
		thread = IvMeasurementThread ( args )
		super ( IvMeasurementWindow, self ) .__init__ ( parent, 2 if args.guardring else 1, args, thread )

		self._ylabel = [u"Pad current in A", u"GR current in A"]
		self.setWindowTitle ( u"IV measurement" )
		logger = logging.getLogger ( u'myLogger' )
