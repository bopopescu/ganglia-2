#/*******************************************************************************
#* Portions Copyright (C) 2008 Novell, Inc. All rights reserved.
#*
#* Redistribution and use in source and binary forms, with or without
#* modification, are permitted provided that the following conditions are met:
#*
#*  - Redistributions of source code must retain the above copyright notice,
#*    this list of conditions and the following disclaimer.
#*
#*  - Redistributions in binary form must reproduce the above copyright notice,
#*    this list of conditions and the following disclaimer in the documentation
#*    and/or other materials provided with the distribution.
#*
#*  - Neither the name of Novell, Inc. nor the names of its
#*    contributors may be used to endorse or promote products derived from this
#*    software without specific prior written permission.
#*
#* THIS SOFTWARE IS PROVIDED BY THE COPYRIGHT HOLDERS AND CONTRIBUTORS ``AS IS''
#* AND ANY EXPRESS OR IMPLIED WARRANTIES, INCLUDING, BUT NOT LIMITED TO, THE
#* IMPLIED WARRANTIES OF MERCHANTABILITY AND FITNESS FOR A PARTICULAR PURPOSE
#* ARE DISCLAIMED. IN NO EVENT SHALL Novell, Inc. OR THE CONTRIBUTORS
#* BE LIABLE FOR ANY DIRECT, INDIRECT, INCIDENTAL, SPECIAL, EXEMPLARY, OR
#* CONSEQUENTIAL DAMAGES (INCLUDING, BUT NOT LIMITED TO, PROCUREMENT OF
#* SUBSTITUTE GOODS OR SERVICES; LOSS OF USE, DATA, OR PROFITS; OR BUSINESS
#* INTERRUPTION) HOWEVER CAUSED AND ON ANY THEORY OF LIABILITY, WHETHER IN
#* CONTRACT, STRICT LIABILITY, OR TORT (INCLUDING NEGLIGENCE OR OTHERWISE)
#* ARISING IN ANY WAY OUT OF THE USE OF THIS SOFTWARE, EVEN IF ADVISED OF THE
#* POSSIBILITY OF SUCH DAMAGE.
#*
#* Authors: Matt Ryan (mrayn novell.com)
#*                  Brad Nicholes (bnicholes novell.com)
#******************************************************************************/

import os
import rrdtool
import logging
from time import time

from Gmetad.gmetad_plugin import GmetadPlugin
from Gmetad.gmetad_config import getConfig, GmetadConfig

def get_plugin():
    ''' All plugins are required to implement this method.  It is used as the factory
        function that instanciates a new plugin instance. '''
    # The plugin configuration ID that is passed in must match the section name 
    #  in the configuration file.
    return RRDPlugin('rrd')

class RRDPlugin(GmetadPlugin):
    ''' This class implements the RRD plugin that stores metric data to RRD files.'''

    RRAS = 'RRAs'
    RRD_ROOTDIR = 'rrd_rootdir'

    # Default RRAs
    _cfgDefaults = {
            RRAS : [
                    'RRA:AVERAGE:0.5:1:244',
                    'RRA:AVERAGE:0.5:24:244',
                    'RRA:AVERAGE:0.5:168:244',
                    'RRA:AVERAGE:0.5:672:244',
                    'RRA:AVERAGE:0.5:5760:374'
            ],
            RRD_ROOTDIR : '/var/lib/ganglia/rrds',
    }

    def __init__(self, cfgid):
        self.rrdpath = None
        self.cfg = None
        self.kwHandlers = None
        self._resetConfig()
        
        # The call to the parent class __init__ must be last
        GmetadPlugin.__init__(self, cfgid)

    def _resetConfig(self):
        self.rrdpath = None
        self.cfg = RRDPlugin._cfgDefaults
        
        self.kwHandlers = {
            RRDPlugin.RRAS : self._parseRRAs,
            RRDPlugin.RRD_ROOTDIR : self._parseRrdRootdir
        }
    
    def _parseConfig(self, cfgdata):
        '''This method overrides the plugin base class method.  It is used to
            parse the plugin specific configuration directives.'''
        for kw,args in cfgdata:
            if self.kwHandlers.has_key(kw):
                self.kwHandlers[kw](args)

    def _parseRrdRootdir(self, arg):
        ''' Parse the RRD root directory directive. '''
        v = arg.strip().strip('"')
        if os.path.isdir(v):
            self.cfg[RRDPlugin.RRD_ROOTDIR] = v

    def _parseRRAs(self, args):
        ''' Parse the RRAs directive. '''
        self.cfg[RRDPlugin.RRAS] = []
        for rraspec in args.split():
            self.cfg[RRDPlugin.RRAS].append(rraspec.strip().strip('"'))
            
    def _checkDir(self, dir):
        ''' This method validates that an RRD directory exists or creates the directory
            if it doesn't exist. '''
        if not os.path.isdir(dir):
            os.mkdir(dir, 0755)
            
    def _createRRD(self, clusterNode, metricNode, rrdPath, step, summary):
        ''' This method creates a new metric RRD file.'''
        
        # Determine the RRD data source type.
        slope = metricNode.getAttr('slope')
        if slope.lower() == 'positive':
            dsType = 'COUNTER'
        else:
            dsType = 'GAUGE'
            
        localTime = clusterNode.getAttr('localtime')
        if localTime is None:
            localTime = int(time())
            
        # Calculate the heartbeat.
        heartbeat = 8*step
        # Format the data source string and add all of the RRDTool arguments to the
        #  args list.
        dsString = 'DS:sum:%s:%d:U:U'%(dsType,heartbeat)
        args = [str(rrdPath), '-b', str(localTime), '-s', str(step), str(dsString)]
        if summary is True:
            dsString = 'DS:num:%s:%d:U:U'%(dsType,heartbeat)
            args.append(str(dsString))
        for rra in self.cfg[RRDPlugin.RRAS]:
            args.append(rra)
        try:
            # Create the RRD file with the supplied args.
            rrdtool.create(*args)
            logging.debug('Created rrd %s'%rrdPath)
        except Exception, e:
            logging.info('Error creating rrd %s - %s'%(rrdPath, str(e)))
        
    def _updateRRD(self, clusterNode, metricNode, rrdPath, summary):
        ''' This method updates an RRD file with current metric values. '''
        # If the node has a time stamp then use it to update the RRD.  Otherwise get
        #  the current timestamp.
        processTime = clusterNode.getAttr('localtime')
        if processTime is None:
            processTime = int(time())
        # If this is a summary RRD, format the summary entry.  Otherwise just use a standard entry
        if summary is True:
            args = [str(rrdPath), '%s:%s:%s'%(str(processTime),str(metricNode.getAttr('sum')),str(metricNode.getAttr('num')))]
        else:
            args = [str(rrdPath), '%s:%s'%(str(processTime),str(metricNode.getAttr('val')))]
        try:
            # Update the RRD file with the current timestamp and value
            rrdtool.update(*args)
            #logging.debug('Updated rrd %s with value %s'%(rrdPath, str(metricNode.getAttr('val'))))
        except Exception, e:
            logging.info('Error updating rrd %s - %s'%(rrdPath, str(e)))

    def start(self):
        '''Called by the engine during initialization to get the plugin going.'''
        #print "RRD start called"
        pass
    
    def stop(self):
        '''Called by the engine during shutdown to allow the plugin to shutdown.'''
        #print "RRD stop called"
        pass

    def notify(self, clusterNode):
        '''Called by the engine when the internal data source has changed.'''
        # Get the current configuration
        gmetadConfig = getConfig()
        # Find the data source configuration entry that matches the cluster name
        for ds in gmetadConfig[GmetadConfig.DATA_SOURCE]:
            if ds.name == clusterNode.getAttr('name'):
                break
        if ds is None:
            logging.info('No matching data source for %s'%clusterNode.getAttr('name'))
            return
        try:
            if clusterNode.getAttr('status') == 'down':
                return
        except AttributeError:
            pass
        # Create the cluster RRD base path and validate it
        clusterPath = '%s/%s'%(self.cfg[RRDPlugin.RRD_ROOTDIR], clusterNode.getAttr('name'))
        if 'GRID' == clusterNode.id:
            clusterPath = '%s/__SummaryInfo__'%clusterPath
        self._checkDir(clusterPath)

        # We do not want to process grid data
        if 'GRID' == clusterNode.id:
            return

        # Update metrics for each host in the cluster
        for hostNode in clusterNode:
            # Create the host RRD base path and validate it.
            hostPath = '%s/%s'%(clusterPath,hostNode.getAttr('name'))
            self._checkDir(hostPath)
            # Update metrics for each host
            for metricNode in hostNode:
                # Don't update metrics that are numeric values.
                if metricNode.getAttr('type') in ['string', 'timestamp']:
                    continue
                # Create the RRD final path and validate it.
                rrdPath = '%s/%s.rrd'%(hostPath, metricNode.getAttr('name'))
                # Create the RRD metric file if it doesn't exist
                if not os.path.isfile(rrdPath):
                    self._createRRD(clusterNode, metricNode, rrdPath, ds.interval, False)
                #need to do some error checking here if the createRRD failed
                # Update the RRD file.
                self._updateRRD(clusterNode, metricNode, rrdPath, False)
        #print "RRD notify called"
