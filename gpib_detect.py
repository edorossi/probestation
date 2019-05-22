#!/usr/bin/env python

from __future__ import absolute_import
import visa
import logging
import serial
import useserial
from sys import platform

class GPIBDetector ( object ) :
	def __init__ ( self ) :
		logger = logging.getLogger ( u'myLogger' )
		resources = [""] * 1
		try :
			self._rm1 = visa.ResourceManager ( )
			resources = self._rm1.list_resources ( )
		except :
			logger.debug ( u"  Failed to open ni-visa" )
		try :
			if useserial.haveserial :
			    self._rm2 = visa.ResourceManager ( u'@py' )
			    resources += self._rm2.list_resources ( )
		except :
			logger.debug ( u"  Failed to open py-visa" )

		self.identifiers = {}
		logger.debug ( u"  Probing devices..." )
		for res in resources:
			logger.debug ( u"   Found %s", res )
			if not ( res.startswith ( u"ASRL" ) or res.startswith ( u"GPIB" ) or res.startswith ( u"USB0" ) ) :
				continue
			if ( res.startswith ( u"ASRL/dev/ttyS" ) ) :
				continue

			dev = None
			if (res.startswith ( u"ASRL" ) or res.startswith ( u"USB" ))and useserial.haveserial :
				logger.debug ( u"   Opening serial connection to %s", res )
				try :
					if (res.startswith ( u"USB0" )):
						dev = self._rm2.open_resource(res)
					else:
						# 5000 msecs needed to catch slow devices...
						dev = self._rm2.open_resource ( res, baud_rate = 19200, data_bits = 8, timeout = 5000 )
                                        
				except :
					logger.debug ( u"   Could not open serial connection to %s", res )
			if res.startswith ( u"GPIB" ) :
				logger.debug ( u"   Opening GPIB connection to %s", res )
				try : 
					dev = self._rm1.open_resource ( res )
				except :
					logger.debug ( u"   Could not open GPIB connection to %s", res )
			if not ( dev == None ) :
				idn = dev.query ( u"*IDN?" )
				logger.debug ( u"   Got device identification: %s", idn )
				self.identifiers[res] = idn
				dev.close ( )

	def get_resname_for ( self, search ) :
		for key, value in self.identifiers.items ( ) :
			if search in value :
				return key
		return None

if __name__ == u"__main__" :
	import pprint

	detector = GPIBDetector ( )

	pprint.pprint ( detector.identifiers )
