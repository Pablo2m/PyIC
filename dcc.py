# -*- encoding: utf-8 -*-
"""
   This program is free software: you can redistribute it and/or modify
   it under the terms of the GNU General Public License as published by
   the Free Software Foundation, either version 3 of the License, or
   (at your option) any later version.

   This program is distributed in the hope that it will be useful,
   but WITHOUT ANY WARRANTY; without even the implied warranty of
   MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
   GNU General Public License for more details.

   You should have received a copy of the GNU General Public License
   along with this program.  If not, see <http://www.gnu.org/licenses/>.
"""

from threading import Thread
import socket
import struct
import logging

# Set up logger for this module
logger = logging.getLogger(__name__)


# For sending 4 byte's throught a socket
def int2uint4(n):
    """Converts an integer to a 4-byte big-endian string using struct.pack."""
    # Pack as an unsigned integer (I) in big-endian format (>)
    return struct.pack('>I', n)

########################################################################
# DCC download thread
class dcc_download(Thread):
    """Handles a DCC file download in a separate thread."""
    
    ####################################################################
    # Constructor
    def __init__(self, 
                 msg,
                 func=None,
                 buffsize=1024):
        """
        Initializes the DCC download thread.

        Args:
            msg (irc_msg): The `irc_msg` object containing parsed DCC offer
                           details (e.g., `msg.file`, `msg.ip`, `msg.port`, 
                           `msg.size`, `msg.turbo`).
            func (callable, optional): A callback function to execute after the
                                     download attempt (completes or fails).
                                     Defaults to None.
            buffsize (int, optional): The buffer size for socket receive
                                      operations during download. Defaults to 1024.
        """
        Thread.__init__(self)
                      
        self.buffsize = buffsize
        self.turbo = msg.turbo
        self.ip = msg.ip
        self.port = msg.port
        self.f = open( msg.file, "wb" )
        self.func = func
        self.size = msg.size



    ####################################################################
    # Here starts the thread
    def run(self):
        """
        Main execution method for the download thread. 
        Connects to the sender, receives data, and writes it to the specified file.
        Handles both standard and turbo DCC sends. The specified file is opened in
        binary write mode ("wb").

        Network operations (`connect`, `recv`, `send`) can raise `socket.error`.
        The optional callback function `func` is called upon completion or error
        if provided.
        """
        sock = socket.socket( socket.AF_INET, socket.SOCK_STREAM )
        
        sock.connect(( self.ip, self.port ))
        r_size = 0
        
        while ( r_size < self.size ) or  ( self.size == -1 ):
            c = sock.recv( self.buffsize )
            if ( not self.turbo ):
                try:
                    r_size += len(c)
                    sock.send(int2uint4(len(c)))
                except socket.error as e:
                    logger.error(f"Socket error during DCC send acknowledgment: {e}")
                    break
                    
            if ( len( c ) < 1 ):
                break
                
            self.f.write( c )
            
        if ( r_size >= self.size ):
            sock.send(int2uint4( 0 ))
            
        self.f.close( )
        sock.close( )
        
        if ( self.func != None ):
            self.func( )


########################################################################
# Cleans the message
def clean_msg(s):
    """Removes specific ASCII control characters (values 1-9) from a string."""
    for c in range(1, 10):
        s = s.replace(chr(c), '')
    return s

########################################################################
# Converts a port number to a string
def ntop(i):
    """Converts a 32-bit integer IP address to its dotted-quad string representation."""
    ip = ""
    # Use integer division //
    ip += str(( i // 16777216 ) % 256 ) + "."
    ip += str(( i // 65536) %256 ) + "."
    ip += str(( i // 256) % 256 ) + "."
    ip += str( i % 256 )
    return ip

########################################################################
# Get DCC offer
def decompose_dcc_offer(m):
    """
    Parses a DCC SEND or DCC TSEND command string to extract parameters.
    Expected format: "DCC <SEND|TSEND> <filename> <ip_int> <port> [size]"
    Filename can be quoted. Size is optional.
    Returns a tuple (ip_str, port, filename, turbo_bool, size_int) or False on error.
    """
    # DCC command strings are typically like:
    # "DCC SEND <filename> <ip_integer> <port> <size>"
    # "DCC SEND \"<filename with spaces>\" <ip_integer> <port> <size>"
    # "DCC TSEND ..." (turbo send, no acknowledgments)
    # Size is optional for some clients.

    if ( "DCC SEND" in m ):
        l = m.index( "DCC SEND" ) # Find start of relevant part
        turbo = False

    else:

        if ( "DCC TSEND" in m ):
            l = m.index("DCC TSEND")
            turbo = True

        else:
            return False

    if ( " " in m ):
        aux = m[ m.index( " ", l + 4 ) : ]
        
        if ( len( aux ) < 1 ):
            return False

        while ( aux[ 0 ] == " " ):
            aux = aux[1:]
            if ( len( aux ) < 1 ):
                return False


        if ( aux [ 0 ] == '"'):
            
            if ( '"' in aux[ 1 : ] ):
            
                fname = aux[ 1 : aux.index( '"', 1 ) ]

                aux = aux[ aux.index( '"', 1 ) + 1 : ]
                
            else:
                return False

        elif ( aux[ 0 ] == "'" ):
            if ( "'" in aux[ 1 : ] ):
                fname = aux[ 1 : aux.index( "'", 1 ) ]
                aux = aux[ aux.index( "'", 1 ) + 1 : ]
        elif ( ' ' in aux ) :
            fname = aux[ : aux.index( " " )]
            aux = aux[aux.index( " " ) + 1 : ]

        else:
            return False

    # To avoid path's in the filename
        fname = fname.split( "/" )[ -1 ]
        fname = fname.split( "\\" )[ -1 ]

        if ( len( aux ) < 1 ):
            return False
            
        while ( aux[ 0 ] == " " ):
            aux = aux[ 1: ]

        if ( len( aux ) > 1 ) and ( " " in aux ):

            ip = int( aux[ : aux.index( " " ) ])

            aux = aux[ aux.index( " " ) + 1 : ]
            port = int( aux[ : aux.index( " " ) ])

            ip = ntop( ip )

            if ( " " in aux ):
                aux = aux[ aux.index( " " ) + 1 : ]
                size = int( aux )
                
                return ( ip, port, fname, turbo, size )

            if ( ip != "" ):
                return ( ip, port, fname, turbo, -1 )

        else:
            return False

    return False
