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

from irc_codes import *
from dcc import *
import logging

# Set up logger for this module
logger = logging.getLogger(__name__)

# Define sets for multiline message type checking
_RPL_SETS_FOR_MULTILINE = {
    "RPL_LIST_TYPES": {RPL_LISTSTART, RPL_LIST, RPL_LISTEND},
    "RPL_MOTD_TYPES": {RPL_MOTDSTART, RPL_MOTD, RPL_ENDOFMOTD},
    "RPL_WHOIS_TYPES": {RPL_WHOISUSER, RPL_WHOISSERVER, RPL_WHOISOPERATOR, RPL_WHOISIDLE, RPL_WHOISCHANNELS, RPL_ENDOFWHOIS},
    "RPL_WHOWAS_TYPES": {RPL_WHOWASUSER, RPL_ENDOFWHOWAS},
    "RPL_WHO_TYPES": {RPL_WHOREPLY, RPL_ENDOFWHO}, # RPL_ENDOFWHO (315) is for WHO replies
    "RPL_NAMES_TYPES": {RPL_NAMEREPLY, RPL_ENDOFNAMES},
    "RPL_LINKS_TYPES": {RPL_LINKS, RPL_ENDOFLINKS},
    "RPL_BANLIST_TYPES": {RPL_BANLIST, RPL_ENDOFBANLIST},
    "RPL_INFO_TYPES": {RPL_INFO, RPL_ENDOFINFO},
    "RPL_USERS_TYPES": {RPL_USERS, RPL_ENDOFUSERS}
}

_MULTILINE_END_MARKERS = {
    RPL_LISTEND, RPL_ENDOFMOTD, RPL_ENDOFWHOIS, RPL_ENDOFWHOWAS,
    RPL_ENDOFWHO, RPL_ENDOFNAMES, RPL_ENDOFLINKS, RPL_ENDOFBANLIST,
    RPL_ENDOFINFO, RPL_ENDOFUSERS
}

_ALL_MULTILINE_MARKERS = set()
for s in _RPL_SETS_FOR_MULTILINE.values():
    _ALL_MULTILINE_MARKERS.update(s)

# Irc message type containing the basic information
class irc_msg(object):
    """
    Represents a parsed IRC message.

    This class takes a raw byte string from an IRC server, decodes it,
    and parses it into its constituent parts: sender (nick and origin),
    command/type, target, and the actual message content. It also handles
    CTCP messages (including DCC offers) and flags for multiline responses.
    """

    ####################################################################
    # Data
    by = "" # Sender nickname
    origin = "" # Sender info
    to = "" # Receiver (you... or the channel)
    private = False # Is client to client
    type = "" # Type of message
    msg = ""
    multiline = False
    multiline_end = False
    ctcp = False
    ctcp_msg = ""
    raw = ""
    
    ####################################################################
    # Constructor
    def __init__(self, s_bytes):
        """
        Parses a raw IRC message (bytes) into its components.

        The raw byte string is decoded using UTF-8 (with replacement for errors).
        The message is then broken down into sender (nick, origin), type (command),
        target(s), and the core message payload. Special handling for CTCP messages
        (including DCC offers) is included. Multiline flags are set based on the
        message type.

        Args:
            s_bytes (bytes): The raw byte string received from the IRC server.
        """
        self.raw_bytes = s_bytes
        s = s_bytes.decode('utf-8', errors='replace') # s is now a string for parsing
        self.raw = s # Store the decoded string version of the raw message
                      
        # Initialize all fields to default/empty states
        self.by = ""
        self.origin = ""
        self.type = ""
        self.to = ""
        self.msg = ""
        # self.multiline and self.multiline_end are set by class default
        # self.ctcp and self.ctcp_msg are set by class default

        # Extracting "FROM" (prefix part of the message)
        if ( s.startswith(":") ): # Use startswith for clarity
            s = s[ 1: ]
            
        i =- 1
        if ( " " in s ):
            i = s.index(" ")

        if ( i < 0 ) or ( i >= len( s )):
            # This indicates a malformed message or a message without a clear sender and command.
            # Examples: ERROR messages from server, or other non-standard lines.
            # Store the entire unparseable line as 'msg' and potentially 'type' if it's a single word.
            # The original code would set self.by, self.origin, self.type, self.to to "" via class defaults.
            self.msg = s # Store the problematic line as the message content.
            # If 's' is a single word, it might be a command like "ERROR"
            if " " not in s:
                self.type = s # Treat as type if no spaces
            return # Stop parsing for this malformed/unrecognized message structure
            
        self.by = s[ :i ]
        s = s[ i + 1 : ]
        i =- 1
        if ( "!" in self.by ):
            i = self.by.index("!")
            
        if ( i >= 0 ) and ( i < len( self.by )):
            
            self.origin = self.by[ i + 1 : ]
            self.by = self.by[ : i ]

        # Extracting "TYPE"
        i =- 1

        if ( " " in s ):
            i = s.index(" ")
            
            
        if ( i < 0 ) or ( i > len( s )):
            # After extracting 'by', 's' should contain 'type' and the rest.
            # If no more spaces, 's' itself might be the type.
            # The original code set type="", to="", msg=s.
            self.type = s # Assume the remainder is the type
            self.to = ""   # No further parts for 'to'
            self.msg = ""  # Or message
            # Multiline flags will be set based on this type below.
            return # Stop further parsing
            
        self.type = s[ : i ]
        s = s[ i + 1 : ]

        # Extracting "TO"
        i=-1
        if ( " " in s ):
            i = s.index(" ")

        if ( i < 0 ) or ( i > len( s )):
             # No space found, means 's' is the 'to' field, and message is empty
            self.to = s
            self.msg = ""
            # CTCP checks below will still run on empty self.msg if needed
        else:
            self.to = s[ :i ]
            s = s[ i + 1 : ]

        if (s.startswith(":") ): # Use startswith for clarity
            s = s[1:]
        # Original code had " :" check, which seems unusual.
        # Python's strip() or lstrip() might be more robust if spaces are an issue.
        # For now, keeping logic close to original:
        elif (s.startswith(" :") and len(s) > 1): # Ensure there's a char after " :"
            s = s[2:]

        self.msg = s

        # Extracting "CTCP"
        # chr(1) is correct here because 's' (and thus self.msg) is now a string
        i=-1
        if ( chr( 1 ) in self.msg ): # Check in self.msg, not s, as s might be empty by now
            # Check specifically in self.msg as per original logic intent
            try:
                i = self.msg.index( chr( 1 ) )
            except ValueError: # Should not happen if 'in' is true, but good practice
                i = -1


        if (i >= 0 ): # Found the first chr(1) at index i in self.msg
            self.ctcp = True
            # Extract the part after the first chr(1)
            potential_ctcp_content = self.msg[i + 1:]
            
            try:
                # Search for the closing chr(1) in this potential content
                closing_ctcp_idx = potential_ctcp_content.index(chr(1))
                # self.ctcp_msg is the part between the two chr(1) characters
                self.ctcp_msg = potential_ctcp_content[:closing_ctcp_idx]
            except ValueError: # No closing chr(1) found
                # As per original logic, if CTCP is not properly terminated with a second chr(1),
                # the message parsing for CTCP specific commands (like DCC) should stop here.
                # Assign what was found (the unterminated part) to ctcp_msg.
                self.ctcp_msg = potential_ctcp_content
                return # Stop further processing for this message

            # If we successfully extracted self.ctcp_msg (it was properly terminated)
            # then proceed to check if it's a DCC offer.
            dcc_params = decompose_dcc_offer(self.ctcp_msg) # self.ctcp_msg is a string
            
            if dcc_params: # If decompose_dcc_offer returned valid parameters
                self.ip = dcc[ 0 ]
                self.port = dcc[ 1 ]
                self.file = ""
                self.turbo = dcc[ 3 ]
                self.size = dcc_params[4] # Corrected from dcc[4] to dcc_params[4]
                try:
                    self.file += dcc_params[2]
                except (TypeError, IndexError) as e:
                    logger.error(f"Error processing DCC filename component '{dcc_params[2]}': {e}")
                    # self.file remains as initialized (""), DCC offer might be unusable
                    pass 
                    
                self.type = DCC_SEND_OFFER # Override message type
                # Note: if we return here, multiline flags won't be set by the new logic below.
                # However, DCC_SEND_OFFER is not a multiline type, so it's fine.
                return # DCC offer processed, no further parsing needed for this message

        # Set multiline flags based on self.type
        # These attributes are initialized to False at the class level.
        if self.type: # Ensure self.type was successfully parsed
            self.multiline_end = self.type in _MULTILINE_END_MARKERS
            self.multiline = self.type in _ALL_MULTILINE_MARKERS


