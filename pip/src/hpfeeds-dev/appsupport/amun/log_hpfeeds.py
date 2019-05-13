"""
[Amun - low interaction honeypot]
Copyright (C) [2013]  [Jan Goebel]

This program is free software; you can redistribute it and/or modify it under the terms of the GNU General Public License as published by the Free Software Foundation; either version 2 of the License, or (at your option) any later version.

This program is distributed in the hope that it will be useful, but WITHOUT ANY WARRANTY; without even the implied warranty of MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE. See the GNU General Public License for more details.

You should have received a copy of the GNU General Public License along with this program; if not, see <http://www.gnu.org/licenses/>
"""

try:
    import psyco ; psyco.full()
    from psyco.classes import *
except ImportError:
    pass

import time
import amun_logging
import amun_config_parser
import base64

#from kippo/hpfeeds.py
import os
import struct
import hashlib
import json
import socket

BUFSIZ = 16384

OP_ERROR        = 0
OP_INFO         = 1
OP_AUTH         = 2
OP_PUBLISH      = 3
OP_SUBSCRIBE    = 4

MAXBUF = 1024**2
SIZES = {
    OP_ERROR: 5+MAXBUF,
    OP_INFO: 5+256+20,
    OP_AUTH: 5+256+20,
    OP_PUBLISH: 5+MAXBUF,
    OP_SUBSCRIBE: 5+256*2,
}

AMUNCHAN = 'amun.events'
#AMUNCHAN = 'HoneyNED'

class BadClient(Exception):
        pass

# packs a string with 1 byte length field
def strpack8(x):
    if isinstance(x, str): x = x.encode('latin1')
    return struct.pack('!B', len(x)) + x

# unpacks a string with 1 byte length field
def strunpack8(x):
    l = x[0]
    return x[1:1+l], x[1+l:]

def msghdr(op, data):
    return struct.pack('!iB', 5+len(data), op) + data
def msgpublish(ident, chan, data):
    return msghdr(OP_PUBLISH, strpack8(ident) + strpack8(chan) + data)
def msgsubscribe(ident, chan):
    if isinstance(chan, str): chan = chan.encode('latin1')
    return msghdr(OP_SUBSCRIBE, strpack8(ident) + chan)
def msgauth(rand, ident, secret):
    hash = hashlib.sha1(bytes(rand)+secret).digest()
    return msghdr(OP_AUTH, strpack8(ident) + hash)

class FeedUnpack(object):
    def __init__(self):
        self.buf = bytearray()
    def __iter__(self):
        return self
    def next(self):
        return self.unpack()
    def feed(self, data):
        self.buf.extend(data)
    def unpack(self):
        if len(self.buf) < 5:
            raise StopIteration('No message.')

        ml, opcode = struct.unpack('!iB', buffer(self.buf,0,5))
        if ml > SIZES.get(opcode, MAXBUF):
            raise BadClient('Not respecting MAXBUF.')

        if len(self.buf) < ml:
            raise StopIteration('No message.')

        data = bytearray(buffer(self.buf, 5, ml-5))
        del self.buf[:ml]
        return opcode, data

class hpclient(object):
    def __init__(self, server, port, ident, secret, debug, loLogger):
        self.debug = debug
        self.log_obj = amun_logging.amun_logging("log_hpfeeds", loLogger)
        if self.debug: self.log_obj.log("log-hpfeeds hpfeeds client init broker {0}:{1}, identifier {2}".format(server, port, ident), 12, "crit", Log=True, display=True)
        self.server, self.port = server, int(port)
        self.ident, self.secret = ident.encode('latin1'), secret.encode('latin1')
        self.unpacker = FeedUnpack()
        self.state = 'INIT'
            
        self.connect()
        self.sendfiles = []
        self.filehandle = None

    def connect(self):
        self.s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        self.s.settimeout(3)
        try: self.s.connect((self.server, self.port))
        except:
            self.log_obj.log("log-hpfeeds hpfeeds client could not connect to broker.", 12, "crit", Log=True, display=True)
            self.s = None
        else:
            self.s.settimeout(None)
            self.handle_established()

    def send(self, data):
        if not self.s: return
        self.s.send(data)

    def close(self):
        self.s.close()
        self.s = None

    def handle_established(self):
        if self.debug: self.log_obj.log("log-hpfeeds hpclient established", 12, "crit", Log=True, display=True)
        while self.state != 'GOTINFO':
            self.read()

        #quickly try to see if there was an error message
        self.s.settimeout(0.5)
        self.read()
        self.s.settimeout(None)

    def read(self):
        if not self.s: return
        try: d = self.s.recv(BUFSIZ)
        except socket.timeout:
            return

        if not d:
            if self.debug: self.log_obj.log("log-hpfeeds hpclient connection closed?", 12, "crit", Log=True, display=True)
            self.close()
            return

        self.unpacker.feed(d)
        try:
            for opcode, data in self.unpacker:
                if self.debug: self.log_obj.log("log-hpfeeds hpclient msg opcode {0} data {1}".format(opcode, data), 12, "crit", Log=True, display=True)
                if opcode == OP_INFO:
                    name, rand = strunpack8(data)
                    if self.debug: self.log_obj.log("log-hpfeeds hpclient server name {0} rand {1}".format(name, rand), 12, "crit", Log=True, display=True)
                    self.send(msgauth(rand, self.ident, self.secret))
                    self.state = 'GOTINFO'

                elif opcode == OP_PUBLISH:
                    ident, data = strunpack8(data)
                    chan, data = strunpack8(data)
                    if self.debug: self.log_obj.log("log-hpfeeds publish to {0} by {1}: {2}".format(chan, ident, data), 12, "crit", Log=True, display=True)

                elif opcode == OP_ERROR:
                    self.log_obj.log("log-hpfeeds errormessage from server: {0}".format(data), 12, "crit", Log=True, display=True)
                else:
                    self.log_obj.log("log-hpfeeds unknown opcode message: {0}".format(opcode), 12, "crit", Log=True, display=True)
        except BadClient:
            self.log_obj.log("log-hpfeeds unpacker error, disconnecting.", 12, "crit", Log=True, display=True)
            self.close()

    def publish(self, channel, **kwargs):
        try:
            self.send(msgpublish(self.ident, channel, json.dumps(kwargs).encode('latin1')))
        except Exception, e:
            self.log_obj.log("log-hpfeeds connection to hpfriends lost: {0}".format(e), 12, "crit", Log=True, display=True)
            self.log_obj.log("log-hpfeeds connecting", 12, "crit", Log=True, display=True)
            self.connect()
            self.send(msgpublish(self.ident, channel, json.dumps(kwargs).encode('latin1')))

    def sendfile(self, filepath):
        # does not read complete binary into memory, read and send chunks
        if not self.filehandle:
            self.sendfileheader(i.file)
            self.sendfiledata()
        else: self.sendfiles.append(filepath)

    def sendfileheader(self, filepath):
        self.filehandle = open(filepath, 'rb')
        fsize = os.stat(filepath).st_size
        headc = strpack8(self.ident) + strpack8(UNIQUECHAN)
        headh = struct.pack('!iB', 5+len(headc)+fsize, OP_PUBLISH)
        self.send(headh + headc)

    def sendfiledata(self):
        tmp = self.filehandle.read(BUFSIZ)
        if not tmp:
            if self.sendfiles:
                fp = self.sendfiles.pop(0)
                self.sendfileheader(fp)
            else:
                self.filehandle = None
                self.handle_io_in(b'')
        else:
            self.send(tmp)

class log:
    def __init__(self):
        try:
            self.log_name = "log hpfeeds"
            conffile = "conf/log-hpfeeds.conf"
            config = amun_config_parser.AmunConfigParser(conffile)
            self.server = config.getSingleValue("server")
            self.port = config.getSingleValue("port")
            self.ident = config.getSingleValue("identifier")
            self.secret = config.getSingleValue("secret")
            self.debug = int(config.getSingleValue("debug"))
            del config
            
        except KeyboardInterrupt:
            raise

    def connectClient(self, loLogger):
        try:
            self.client = hpclient(self.server, self.port, self.ident, self.secret, self.debug, loLogger)
            return True
        except KeyboardInterrupt:
            raise

    def initialConnection(self, attackerIP, attackerPort, victimIP, victimPort, identifier, initialConnectionsDict, loLogger):
        try:
            self.log_obj = amun_logging.amun_logging("log_hpfeeds", loLogger)
            if self.connectClient(loLogger):
                self.client.publish(AMUNCHAN,
                    attackerIP=attackerIP,
                    attackerPort=attackerPort,
                    victimIP=victimIP,
                    victimPort=victimPort
                )
                        
        except KeyboardInterrupt:
            raise

    def incoming(self, attackerIP, attackerPort, victimIP, victimPort, vulnName, timestamp, downloadMethod, loLogger, attackerID, shellcodeName):
        try:
            self.log_obj = amun_logging.amun_logging("log_hpfeeds", loLogger)
            if self.connectClient(loLogger):
                self.client.publish(AMUNCHAN,
                    attackerIP=attackerIP,
                    attackerPort=attackerPort,
                    victimIP=victimIP,
                    victimPort=victimPort,
                    vulnName=vulnName, timestamp=timestamp, downloadMethod=downloadMethod, attackerID=attackerID, shellcodeName=shellcodeName
                )
                        
        except KeyboardInterrupt:
            raise


    def successfullSubmission(self, attackerIP, attackerPort, victimIP, downloadURL, md5hash, data, filelength, downMethod, loLogger, vulnName, fexists):
        try:
            self.log_obj = amun_logging.amun_logging("log_hpfeeds", loLogger)
            if self.connectClient(loLogger):
                self.client.publish(AMUNCHAN,
                    attackerIP=attackerIP,
                    attackerPort=attackerPort,
                    victimIP=victimIP,
                    victimPort=victimPort,
                    downloadURL=downloadURL, md5hash=md5hash, data=data, filelength=filelength, downMethod=downMethod, vulnName=vulnName, fexists=fexists
                )
                        
        except KeyboardInterrupt:
            raise
