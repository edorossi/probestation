#!/usr/bin/env python

from __future__ import absolute_import
import logging

try:
    from PyQt5 import QtWidgets as QtW
    from PyQt5 import QtCore
except ImportError as e :
    from PyQt4 import QtGui as QtW
    from PyQt4 import QtCore

import os
from collections import namedtuple
from pyvisa.errors import VisaIOError

import gpib_detect
from iv_measurement import IvMeasurementWindow
from cv_measurement import CvMeasurementWindow
from strip_measurement import StripMeasurementWindow

import useserial

def createSpin ( lower, upper, step, value, decimals, suffix, tooltip = u"" ) :
	spin = QtW.QDoubleSpinBox ( )
	spin.setRange ( lower, upper )
	spin.setSingleStep ( step )
	spin.setValue ( value )
	spin.setDecimals ( decimals )
	spin.setSuffix ( suffix )
	if tooltip :
		spin.setToolTip ( tooltip )
	return spin

class SerialEnableWidget ( QtW.QGroupBox ) :
	def __init__ ( self ) :
		super ( SerialEnableWidget, self ) .__init__ ( u"Device communication" )

		form = QtW.QFormLayout ( )
		self.setLayout ( form )

		self._serialenable_cb = QtW.QCheckBox ( )

		form.addRow ( u"Enable serial device connection", self._serialenable_cb )

	def getStatus ( self ) :
		enableserial = self._serialenable_cb.isChecked ( )
		return ( enableserial )

class VoltsrcGroupWidget ( QtW.QGroupBox ) :
	def __init__ ( self ) :
		super ( VoltsrcGroupWidget, self ) .__init__ ( u"Voltage source" )

		form = QtW.QFormLayout ( )
		self.setLayout ( form )

		self._start_spin = createSpin ( -1000, 1000, 0.01, 0, 2, u" V", u"Source voltage to start with" )
		self._end_spin = createSpin ( -1000, 1000, 0.01, -1, 2, u" V", u"Source voltage to end with" )
		self._step_spin = createSpin ( 0, 1000, 0.01, 0.1, 2, u" V", u"Source voltage difference between taking measurements" )
		self._sleep_spin = createSpin ( 0, 100, 1, 1, 1, u" s", u"Time to wait between setting the source voltage and taking the measurement" )
		self._compliance_spin = createSpin ( 0.1, 1000, 1, 10, 1, u" \u03BCA", u"If the compliance current is reached by one of the measured currents, the voltage source is immediately turned off." )

		form.addRow ( u"Start voltage", self._start_spin )
		form.addRow ( u"End voltage", self._end_spin )
		form.addRow ( u"Abs step", self._step_spin )
		form.addRow ( u"Wait time", self._sleep_spin )
		form.addRow ( u"Abs compliance current", self._compliance_spin )

	def getVoltages ( self ) :
		start = self._start_spin.value ( )
		end = self._end_spin.value ( )
		step = self._step_spin.value ( )
		sleeptime = self._sleep_spin.value ( )
		compcurrent = self._compliance_spin.value ( ) * 1e-6

		return ( start, end, step, sleeptime, compcurrent )

class GuardMeasWidget ( QtW.QGroupBox ) :
	def __init__ ( self ) :
		super ( GuardMeasWidget, self ) .__init__ ( u"Guard ring" )

		form = QtW.QFormLayout ( )
		self.setLayout ( form )

		self._guardring_cb = QtW.QCheckBox ( )

		form.addRow ( u"Enable guard ring measurement", self._guardring_cb )

	def getStatus ( self ) :
		guardring = self._guardring_cb.isChecked ( )
		return ( guardring )

class FreqGroupWidget ( QtW.QGroupBox ) :
	def __init__ ( self ) :
		super ( FreqGroupWidget, self ) .__init__ ( u"LCR parameters" )

		form = QtW.QFormLayout ( )
		self.setLayout ( form )

		self._freq_spin = createSpin ( 0.02, 2000, 0.5, 1, 2, u" kHz" )
		form.addRow ( u"Frequency", self._freq_spin )

		self._volt_spin = createSpin ( 0, 20, 0.5, 1, 2, u" V" )
		form.addRow ( u"AC Voltage level", self._volt_spin )

	def getSettings ( self ):
		freq = self._freq_spin.value ( ) * 1e3
		volt = self._volt_spin.value ( )

		return ( freq, volt )

class StripGroupWidget ( QtW.QGroupBox ) :
	def __init__ ( self ) :
		super ( StripGroupWidget, self ) .__init__ ( u"Strip Measurement" )

		form = QtW.QFormLayout ( )
		self.setLayout ( form )

		self._select_r = QtW.QComboBox ( )
		self._select_r.addItems ( ["Capacitance", "Resistance/Impedance"] )
		form.addRow ( u"Measurement Type", self._select_r )

	def getSettings ( self ):
		select = self._select_r.currentText ( )

		return ( select )

class DirectoryLayout ( QtW.QHBoxLayout ):
	def __init__ ( self, directory, parent_win ) :
		super ( DirectoryLayout, self ) .__init__ ( )

		self._parent_win = parent_win

		self._label = QtW.QLabel ( u"Output folder: " )
		self.addWidget ( self._label )
		self._edit = QtW.QLineEdit ( directory )
		self._edit.setReadOnly ( True )
		self.addWidget ( self._edit )
		self._browse = QtW.QPushButton ( u"Browse..." )
		self._browse.clicked.connect ( self._onBrowseClicked )
		self.addWidget ( self._browse )

	def _onBrowseClicked ( self ) :
		new_dir = QtCore.QDir.toNativeSeparators ( QtW.QFileDialog.getExistingDirectory ( self._parent_win, u"", self.getOutputDir ( ) ) )
		if new_dir :
			self._edit.setText ( new_dir )

	def getOutputDir ( self ) :
		return self._edit.text ( )

MeasurementArgs = namedtuple ( u"MeasurementArgs", [u"type", u"devname_hv", u"devname_kei6482", u"devname_agiE4980A", u"start", u"end", u"step", u"compcurrent", u"guardring", u"resistance", u"frequency", u"deltavolt", u"sleep", u"output_dir"] )

class IvTab ( QtW.QWidget ) :
	def __init__ ( self, parent_win, output_dir ) :
		super ( IvTab, self ) .__init__ ( )

		self._parent_win = parent_win

		vbox = QtW.QVBoxLayout ( )
		self.setLayout ( vbox )

		self._serial = SerialEnableWidget ( )
		vbox.addWidget ( self._serial )

		self._voltsrc = VoltsrcGroupWidget ( )
		vbox.addWidget ( self._voltsrc )

		self._guard = GuardMeasWidget ( )
		vbox.addWidget ( self._guard )

		vbox.addStretch ( 1 )

		self._browse_layout = DirectoryLayout ( output_dir, self._parent_win )
		vbox.addLayout ( self._browse_layout )

		hbox = QtW.QHBoxLayout ( )
		hbox.addStretch ( 1 )
		vbox.addLayout ( hbox )
		self._start_button = QtW.QPushButton ( u"Start" )
		self._start_button.setToolTip ( u"Start the measurement" )
		self._start_button.resize ( self._start_button.sizeHint ( ) )
		self._start_button.clicked.connect ( self._onStartClicked )
		hbox.addWidget ( self._start_button )

	def _onStartClicked ( self ) :
		if self._parent_win.measurementIsRunning ( ) :
			self._parent_win.showErrorDialog ( u"Measurement is currently running." )
			return

		if not options.debug :
			check = QtW.QMessageBox.question ( self, u"Warning", u"Is the CV/IV box set to IV?", QtW.QMessageBox.Yes, QtW.QMessageBox.No )
			if check == QtW.QMessageBox.No :
				return

		start, end, step, sleeptime, compcurrent = self._voltsrc.getVoltages ( )
		if step <= 0 :
			self._parent_win.showErrorDialog ( u"Abs step needs to be positive." )
			return
		if abs ( start ) > 1000 or abs ( end ) > 1000 :
			self._parent_win.showErrorDialog ( u"Voltage can't be larger than 1000 V." )
			return
		if not 0 <= sleeptime :
			self._parent_win.showErrorDialog ( u"Invalid sleep time." )
			return

		serialenable = self._serial.getStatus ( )

		guardring = self._guard.getStatus ( )

		if compcurrent <= 0 :
			self._parent_win.showErrorDialog ( u"Compliance current needs to be positive." )
			return

		output_dir = self._browse_layout.getOutputDir ( )
		if not os.path.isdir ( output_dir ) or not os.access ( output_dir, os.W_OK ) :
			self._parent_win.showErrorDialog ( u"Invalid output directory." )
			return

		try :
			if serialenable :
				useserial.haveserial = True
			detector = gpib_detect.GPIBDetector ( )
			kei6517b_devname = detector.get_resname_for ( u"KEITHLEY INSTRUMENTS INC.,MODEL 6517B" )
			kei2410_devname = detector.get_resname_for ( u"KEITHLEY INSTRUMENTS INC.,MODEL 2410" )
			if kei6517b_devname is None :
				hvdev_devname = kei2410_devname
				logger.debug ( u"  Couldn't find Keithley 6517B, trying Keithley 2410 for HV." )
			if kei2410_devname is None :
				hvdev_devname = kei6517b_devname
				logger.debug ( u"  Couldn't find Keithley 2410, trying Keithley 6517B for HV." )
			if ( kei6517b_devname is not None and kei2410_devname is not None) :
				self._parent_win.showErrorDialog ( u"I found both Keithley 6517B and Keithley 2410!<br><br>I don't know which to use!" )
				return
			if ( kei6517b_devname is None and kei2410_devname is None ) :
				self._parent_win.showErrorDialog ( u"Could not find Keithley 6517B or Keithley 2410." )
				return
			if guardring :
				kei6482_devname = detector.get_resname_for ( u"KEITHLEY INSTRUMENTS INC.,MODEL 6482" )
				if kei6482_devname is None :
					self._parent_win.showErrorDialog ( u"Could not find Keithley 6482." )
					return
			else :
				kei6482_devname = None
		except VisaIOError :
			self._parent_win.showErrorDialog ( u"Could not connect to GPIB/serial devices." )
			return

		args = MeasurementArgs ( u"IV", hvdev_devname, kei6482_devname, None, start, end, step, compcurrent, guardring, None, None, None, sleeptime, output_dir )
		self._parent_win.startMeasurement ( args )

class CvTab ( QtW.QWidget ) :
	def __init__ ( self, parent_win, output_dir ) :
		super ( CvTab, self ) .__init__ ( )

		self._parent_win = parent_win

		vbox = QtW.QVBoxLayout ( )
		self.setLayout ( vbox )

		self._serial = SerialEnableWidget ( )
		vbox.addWidget ( self._serial )

		self._voltsrc = VoltsrcGroupWidget ( )
		vbox.addWidget ( self._voltsrc )

		self._freqsettings = FreqGroupWidget ( )
		vbox.addWidget ( self._freqsettings )

		vbox.addStretch ( 1 )

		self._browse_layout = DirectoryLayout ( output_dir, self._parent_win )
		vbox.addLayout ( self._browse_layout )

		hbox = QtW.QHBoxLayout ( )
		hbox.addStretch ( 1 )
		vbox.addLayout ( hbox )
		self._start_button = QtW.QPushButton ( u"Start" )
		self._start_button.setToolTip ( u"Start the measurement" )
		self._start_button.resize ( self._start_button.sizeHint ( ) )
		self._start_button.clicked.connect ( self._onStartClicked )
		hbox.addWidget ( self._start_button )

	def _onStartClicked ( self ) :
		if self._parent_win.measurementIsRunning ( ) :
			self._parent_win.showErrorDialog ( u"Measurement is currently running." )
			return

		if not options.debug :
			check = QtW.QMessageBox.question ( self, u"Warning", u"Is the CV/IV box set to both CV and External?", QtW.QMessageBox.Yes, QtW.QMessageBox.No )
			if check == QtW.QMessageBox.No :
				return

		start, end, step, sleeptime, compcurrent = self._voltsrc.getVoltages ( )
		if step <= 0 :
			self._parent_win.showErrorDialog ( u"Abs step needs to be positive." )
			return
		if abs ( start ) > 1000 or abs ( end ) > 1000 :
			self._parent_win.showErrorDialog ( u"Voltage can't be larger than 1000 V." )
			return
		if not 0 <= sleeptime :
			self._parent_win.showErrorDialog ( u"Invalid sleep time." )
			return

		serialenable = self._serial.getStatus ( )

		freq, volt = self._freqsettings.getSettings ( )
		if not 20 <= freq <= 2e6 :
			self._parent_win.showErrorDialog ( u"Frequency must be between 20 Hz and 2 MHz." )
			return
		if not 0 <= volt <= 20 :
			self._parent_win.showErrorDialog ( u"AC voltage must be between 0 V and 20 V." )
			return

		if compcurrent <= 0 :
			self._parent_win.showErrorDialog ( u"Compliance current needs to be positive." )
			return

		output_dir = self._browse_layout.getOutputDir ( )
		if not os.path.isdir ( output_dir ) or not os.access ( output_dir, os.W_OK ) :
			self._parent_win.showErrorDialog ( u"Invalid output directory." )
			return

		try :
			if serialenable :
				useserial.haveserial = True
			detector = gpib_detect.GPIBDetector ( )
			kei6517b_devname = detector.get_resname_for ( u"KEITHLEY INSTRUMENTS INC.,MODEL 6517B" )
			kei2410_devname = detector.get_resname_for ( u"KEITHLEY INSTRUMENTS INC.,MODEL 2410" )
			if kei6517b_devname is None :
				hvdev_devname = kei2410_devname
				logger.debug ( u"  Couldn't find Keithley 6517B, trying Keithley 2410 for HV." )
			if kei2410_devname is None :
				hvdev_devname = kei6517b_devname
				logger.debug ( u"  Couldn't find Keithley 2410, trying Keithley 6517B for HV." )
			if ( kei6517b_devname is not None and kei2410_devname is not None) :
				self._parent_win.showErrorDialog ( u"I found both Keithley 6517B and Keithley 2410!<br><br>I don't know which to use!" )
				return
			if ( kei6517b_devname is None and kei2410_devname is None ) :
				self._parent_win.showErrorDialog ( u"Could not find Keithley 6517B or Keithley 2410." )
				return
			agie4980a_devname = detector.get_resname_for ( u"Keysight Technologies,E4980A" )
			if agie4980a_devname is None :
				self._parent_win.showErrorDialog ( u"Could not find Keysight E4980A." )
				return
		except VisaIOError :
			self._parent_win.showErrorDialog ( u"Could not connect to GPIB/serial devices." )
			return

		# CV box adds 1KOhm -> compcurrent goes down...
		args = MeasurementArgs ( u"CV", hvdev_devname, None, agie4980a_devname, start, end, step, compcurrent * 1000.0, None, None, freq, volt, sleeptime, output_dir )
		self._parent_win.startMeasurement ( args )

class StripTab ( QtW.QWidget ) :
	def __init__ ( self, parent_win, output_dir ) :
		super ( StripTab, self ) .__init__ ( )

		self._parent_win = parent_win

		vbox = QtW.QVBoxLayout ( )
		self.setLayout ( vbox )

		self._serial = SerialEnableWidget ( )
		vbox.addWidget ( self._serial )

		self._voltsrc = VoltsrcGroupWidget ( )
		vbox.addWidget ( self._voltsrc )

		self._freqsettings = FreqGroupWidget ( )
		vbox.addWidget ( self._freqsettings )

		self._stripsettings = StripGroupWidget ( )
		vbox.addWidget ( self._stripsettings )

		vbox.addStretch ( 1 )

		self._browse_layout = DirectoryLayout ( output_dir, self._parent_win )
		vbox.addLayout ( self._browse_layout )

		hbox = QtW.QHBoxLayout ( )
		hbox.addStretch ( 1 )
		vbox.addLayout ( hbox )
		self._start_button = QtW.QPushButton ( u"Start" )
		self._start_button.setToolTip ( u"Start the measurement" )
		self._start_button.resize ( self._start_button.sizeHint ( ) )
		self._start_button.clicked.connect ( self._onStartClicked )
		hbox.addWidget ( self._start_button )

	def _onStartClicked ( self ) :
		if self._parent_win.measurementIsRunning ( ) :
			self._parent_win.showErrorDialog ( u"Measurement is currently running." )
			return

		if not options.debug :
			check = QtW.QMessageBox.question ( self, u"Warning", u"Is the CV/IV box set to both IV and C<sub>int</sub>/R<sub>int</sub>?", QtW.QMessageBox.Yes, QtW.QMessageBox.No )
			if check == QtW.QMessageBox.No :
				return

		start, end, step, sleeptime, compcurrent = self._voltsrc.getVoltages ( )
		if step <= 0 :
			self._parent_win.showErrorDialog ( u"Abs step needs to be positive." )
			return
		if abs ( start ) > 1000 or abs ( end ) > 1000 :
			self._parent_win.showErrorDialog ( u"Voltage can't be larger than 1000 V." )
			return
		if not 0 <= sleeptime :
			self._parent_win.showErrorDialog ( u"Invalid sleep time." )
			return

		serialenable = self._serial.getStatus ( )

		freq, volt = self._freqsettings.getSettings ( )
		if not 20 <= freq <= 2e6 :
			self._parent_win.showErrorDialog ( u"Frequency must be between 20 Hz and 2 MHz." )
			return
		if not 0 <= volt <= 20 :
			self._parent_win.showErrorDialog ( u"AC voltage must be between 0 V and 20 V." )
			return

		if ( self._stripsettings.getSettings ( ) == u"Resistance/Impedance" ) :
			resistance = True
		else :
			resistance = False

		if compcurrent <= 0 :
			self._parent_win.showErrorDialog ( u"Compliance current needs to be positive." )
			return

		output_dir = self._browse_layout.getOutputDir ( )
		if not os.path.isdir ( output_dir ) or not os.access ( output_dir, os.W_OK ) :
			self._parent_win.showErrorDialog ( u"Invalid output directory." )
			return

		try :
			if serialenable :
				useserial.haveserial = True
			detector = gpib_detect.GPIBDetector ( )
			kei6517b_devname = detector.get_resname_for ( u"KEITHLEY INSTRUMENTS INC.,MODEL 6517B" )
			kei2410_devname = detector.get_resname_for ( u"KEITHLEY INSTRUMENTS INC.,MODEL 2410" )
			if kei6517b_devname is None :
				hvdev_devname = kei2410_devname
				logger.debug ( u"  Couldn't find Keithley 6517B, trying Keithley 2410 for HV." )
			if kei2410_devname is None :
				hvdev_devname = kei6517b_devname
				logger.debug ( u"  Couldn't find Keithley 2410, trying Keithley 6517B for HV." )
			if ( kei6517b_devname is not None and kei2410_devname is not None) :
				self._parent_win.showErrorDialog ( u"I found both Keithley 6517B and Keithley 2410!<br><br>I don't know which to use!" )
				return
			if ( kei6517b_devname is None and kei2410_devname is None ) :
				self._parent_win.showErrorDialog ( u"Could not find Keithley 6517B or Keithley 2410." )
				return
			agie4980a_devname = detector.get_resname_for ( u"Keysight Technologies,E4980A" )
			if agie4980a_devname is None :
				self._parent_win.showErrorDialog ( u"Could not find Keysight E4980A." )
				return
		except VisaIOError :
			self._parent_win.showErrorDialog ( u"Could not connect to GPIB/serial devices." )
			return

		# CV box adds 1KOhm -> compcurrent goes down...
		args = MeasurementArgs ( u"Strip", hvdev_devname, None, agie4980a_devname, start, end, step, compcurrent * 1000.0, None, resistance, freq, volt, sleeptime, output_dir )
		self._parent_win.startMeasurement ( args )

class MainWindow ( QtW.QMainWindow ) :
	def __init__ ( self, output_dir ) :
		super ( MainWindow, self ) .__init__ ( )

		self.setWindowTitle ( u"Probe Station Software" )

		self._tabwidget = QtW.QTabWidget ( )
		self.setCentralWidget ( self._tabwidget )

		self._ivtab = IvTab ( self, output_dir )
		self._tabwidget.addTab ( self._ivtab, u"IV" )

		self._cvtab = CvTab ( self, output_dir )
		self._tabwidget.addTab ( self._cvtab, u"CV" )

		self._striptab = StripTab ( self, output_dir )
		self._tabwidget.addTab ( self._striptab, u"Strip" )

		self._mwin = None

	def measurementIsRunning ( self ) :
		return not self._mwin is None and self._mwin.isRunning ( )

	def startMeasurement ( self, args ) :
		if args.type == u"IV" :
			self._mwin = IvMeasurementWindow ( self, args )
		elif args.type == u"CV" :
			self._mwin = CvMeasurementWindow ( self, args )
		elif args.type == u"Strip" :
			self._mwin = StripMeasurementWindow ( self, args )
		else :
			raise NotImplementedError ( args.type )
		self._mwin.setWindowModality ( QtCore.Qt.WindowModal )
		self._mwin.set_absolute ( True )
		self._mwin.start ( )

	def showErrorDialog ( self, message ) :
		reply = QtW.QMessageBox.critical ( self, u"Error", message, QtW.QMessageBox.Ok, QtW.QMessageBox.Ok )

if __name__ == u"__main__" :
	import sys
	import optparse

	app = QtW.QApplication ( sys.argv )
	if len ( sys.argv ) > 1 and os.path.isdir ( sys.argv[1] ) :
		output_dir = sys.argv[1]
	else:
		output_dir = os.getcwd ( )

	usage = u"Usage: python %prog [options] <default storage path>"
	description = u"If no default storage path is specified, the current directory is used."
	parser = optparse.OptionParser ( usage = usage, description = description )
	parser.add_option ( u"-d", u"--debug", action = u"store_true", dest = u"debug", help = u"debug flag, enables more verbose console output" )
	options, args = parser.parse_args ( )
	logger = logging.getLogger ( u'myLogger' )
	ch = logging.StreamHandler ( )
	logger.addHandler ( ch )
	logger.setLevel ( logging.INFO )
	ch.setLevel ( logging.INFO )
	if options.debug :
		logger.setLevel ( logging.DEBUG )
		ch.setLevel ( logging.DEBUG )
		logger.debug ( u"Running in DEBUG mode!" )
		logger.debug ( u" Output path is: %s", output_dir )

	useserial.init ( )
	win = MainWindow ( output_dir )
	win.show ( )
	sys.exit ( app.exec_ ( ) )
