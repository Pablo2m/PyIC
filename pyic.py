# -*- encoding: utf-8 -*-
"""
   Simple Python Irc Client library

   Copyright (c) 2010 kenkeiras <kenkeiras@gmail.com>
   Under GPLv3 license (or later)

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

from irc_msg import *
from irc_codes import *
import socket
import ssl # Moved import ssl to the top

VERSION = "PyIC 0.2"

def clean_usr(usr):
    """
    Removes common prefix characters (like '@') from a user nick.

    Args:
        usr (str): The user nickname, possibly prefixed (e.g., "@nickname").

    Returns:
        str: The cleaned nickname.
    """
    return usr.replace( "@", "" ) # Simple replacement, can be expanded if other prefixes are common.

# Retrieve a single line from the socket
def getline(sock):
    """
    Reads a single line (ending in b'\\n') from a socket.

    This function reads byte by byte from the socket until a newline character
    (b'\\n') is encountered. It handles potential connection closure by the peer
    and strips carriage return characters (b'\\r').

    Args:
        sock (socket.socket): The socket object to read from.

    Returns:
        bytes: The raw line read from the socket, excluding the newline
               and any carriage returns.

    Raises:
        socket.error: If a socket error occurs during recv (e.g., connection
                      reset) or if the connection is closed by the peer.
    """
    l = b"" # Initialize as bytes
    while 1:
        try:
            c = sock.recv(1) # c is bytes
        except socket.error as e:
            # Catch socket errors during recv, e.g., connection reset
            raise socket.error(f"Socket error during recv: {e}")

        if not c: # Empty byte string indicates connection closed by peer
            raise socket.error("Connection closed by peer")
            
        if ( c == b"\n" ): # Compare bytes with bytes
            break
            
        elif ( c != b"\r" ): # Compare bytes with bytes
            l += c # Concatenate bytes
    return l # Returns a bytes object

########################################################################
# Irc Client main class
class irc_client(object):
    """
    Provides a client for interacting with IRC (Internet Relay Chat) servers.

    This class handles connection, message sending/receiving, parsing of common
    IRC commands and replies, and basic features like WHOIS, channel/user listing,
    and DCC initiation (via irc_msg parsing).
    """
    motd = ""
    msgBuff = []
    
    ####################################################################
    # Shows Message Of The Day
    def get_motd(self):
        """
        Returns the Message Of The Day (MOTD) received from the server.

        The MOTD is accumulated during the initial connection phase.

        Returns:
            str: The MOTD as a multi-line string.
        """
        return self.motd

    ####################################################################
    # Set's channel mode
    def set_chanmode(self, channel, mode, data=None):
        """
        Sets a mode on a channel.

        Args:
            channel (str): The target channel (e.g., "#mychannel").
            mode (str): The mode string to apply (e.g., "+m", "-o nick").
            data (str, optional): Additional data for the mode, if required
                                  (e.g., a nickname for modes like +o).
                                  Defaults to None.
        """
        if data is None: # Pythonic check for None
            self.sock.send(f"MODE {channel} {mode}\r\n".encode('utf-8'))
        else:
            self.sock.send(f"MODE {channel} {mode} {data}\r\n".encode('utf-8'))

    ####################################################################
    # Set's user own mode
    def set_mode(self, mode):
        """
        Sets a user mode for the client's own nickname.

        Args:
            mode (str): The mode string to apply (e.g., "+i" for invisible).
        """
        self.sock.send(f"MODE {self.nick} {mode}\r\n".encode('utf-8'))

    ####################################################################
    # Send's a ping to a server or user 
    # (have to check messages for the answer)
    def ping(self, to):
        """
        Sends a PING command to a target (server or user).

        The recipient should respond with a PONG. This is often used to check
        if a user is still connected or to measure lag to the server.

        Args:
            to (str): The target of the PING (e.g., a server name or a nickname).
        """
        self.sock.send(f"PING {to}\r\n".encode('utf-8'))

    ####################################################################
    # Collect's WHOIS/WHOWAS data
    def collect_who_data(self):
        """
        Collects multi-line WHOIS or WHOWAS reply data.

        Continuously fetches messages until an end-of-WHOIS/WHOWAS marker
        (or an error like ERR_NOSUCHNICK) is received. Parses relevant
        RPL messages to build a dictionary of user data.

        Returns:
            dict: A dictionary containing the collected WHOIS/WHOWAS information.
        """
        m = self.getmsg( True )
        data = { 'channels': [ ] }
        while ( m.type != RPL_ENDOFWHOWAS ) and \
              ( m.type != RPL_ENDOFWHOIS  ) and \
              ( m.type != ERR_NOSUCHNICK  ):
                               
            if ( m.type == RPL_WHOISUSER ): # Target nick user host * :Real name
                parts = m.msg.split(":", 1)
                info_fields = parts[0].strip().split(" ")
                if len(info_fields) >= 3:
                    data['nick'] = info_fields[0]
                    data['user'] = info_fields[1]
                    data['host'] = info_fields[2]
                if len(parts) > 1:
                    data['real_name'] = parts[1]
                
            elif ( m.type == RPL_WHOWASUSER ): # Target nick user host * :Real name
                parts = m.msg.split(":", 1)
                info_fields = parts[0].strip().split(" ")
                if len(info_fields) >= 3:
                    data['nick'] = info_fields[0]
                    data['user'] = info_fields[1]
                    data['host'] = info_fields[2]
                if len(parts) > 1:
                    data['real_name'] = parts[1]
                
            elif ( m.type == RPL_WHOISSERVER ): # Target nick server :Server info
                parts = m.msg.split(":", 1)
                info_fields = parts[0].strip().split(" ")
                if len(info_fields) >= 2: # Expected: <nick> <server_name>
                    # data['nick'] = info_fields[0] # nick is known from context
                    data['server'] = info_fields[1]
                if len(parts) > 1:
                    data['server_info'] = parts[1]

            elif ( m.type == RPL_WHOISOPERATOR ): # Target nick :is an IRC operator
                 data[ 'isOp' ] = True # The message itself is just an affirmation
                
            elif ( m.type == RPL_WHOISIDLE ): # Target nick seconds signon :comment
                parts = m.msg.split(":", 1)
                info_fields = parts[0].strip().split(" ")
                if len(info_fields) >= 2: # Expected: <nick> <seconds> <signon_timestamp>
                    # data['nick'] = info_fields[0]
                    data['idle'] = info_fields[1] # Idle time in seconds
                    if len(info_fields) >=3: # signon time might be optional by some servers
                        data['signon'] = info_fields[2] 
                # The part after colon is typically not used by clients for idle time
                # but could be 'seconds signon' if server formats differently.
                # For simplicity, we assume the first numeric part is idle seconds.

            elif ( m.type == RPL_WHOISCHANNELS ): # Target nick :{[@|+]channel }
                parts = m.msg.split(":", 1)
                if len(parts) > 1:
                    data['channels'].extend(parts[1].strip().split())

            else:
                self.msgBuff.append( m )
                
            m = self.getmsg( True )
            
        return data

    ####################################################################
    # Ask's for user information
    def send_whois(self, user):
        """
        Sends a WHOIS command to the server for a specified user.

        This is typically an internal helper method; `whois()` is the
        public interface for fetching and parsing WHOIS data.

        Args:
            user (str): The nickname of the user to query.
        """
        self.sock.send(f"WHOIS {user}\r\n".encode('utf-8'))

    ####################################################################
    # Reads for user information
    def whois(self, user):
        """
        Performs a WHOIS query for a given user.

        Args:
            user (str): The nickname of the user to query.

        Returns:
            dict: A dictionary containing the WHOIS information. 
                  Keys might include 'nick', 'user', 'host', 'real_name', 
                  'server', 'server_info', 'isOp', 'idle', 'signon', 'channels'.
                  Presence of keys depends on server response and user status.
        """
        self.send_whois( user )
        
        data = self.collect_who_data( )
           
        return data

    ####################################################################
    # Ask's for user (that no longer exists) information
    def send_whowas(self, user):
        """
        Sends a WHOWAS command to the server for a specified user.

        WHOWAS queries information about a nickname that is no longer in use
        (e.g., user quit or changed nick).

        Args:
            user (str): The nickname to query.
        """
        self.sock.send(f"WHOWAS {user}\r\n".encode('utf-8'))
        
    ####################################################################
    # Reads for former user information
    def whowas(self, user):
        """
        Performs a WHOWAS query for a given user.

        Args:
            user (str): The nickname to query (must not be currently online).

        Returns:
            dict: A dictionary containing the WHOWAS information, similar in
                  structure to `whois()` results.
        """
        self.send_whowas( user )
        
        data = self.collect_who_data( )
        
        return data
    
    ####################################################################
    # Set's a channel topic
    def set_topic(self, channel, topic):
        """
        Sets the topic for a specified channel.

        Requires appropriate channel privileges.

        Args:
            channel (str): The target channel (e.g., "#mychannel").
            topic (str): The new topic string.
        """
        self.sock.send(f"TOPIC {channel} :{topic}\r\n".encode('utf-8'))

    ####################################################################
    # Retrieves a channel topic (has to check messages then)
    def retr_topic(self, channel):
        """
        Sends a TOPIC command to retrieve the topic of a channel.

        This is typically an internal helper. `get_topic()` is the public
        interface for fetching and returning the topic.

        Args:
            channel (str): The channel whose topic is to be retrieved.
        """
        self.sock.send(f"TOPIC {channel}\r\n".encode('utf-8'))

    ####################################################################
    # Reads the current topic on a channel
    def get_topic(self, channel):
        """
        Retrieves the current topic of the specified channel.

        Args:
            channel (str): The name of the channel.

        Returns:
            str: The channel topic.
            False: If no topic is set (RPL_NOTOPIC received).
        """
        self.retr_topic( channel )
        while ( True ):
            m = self.getmsg( True )
            if ( m.type == RPL_TOPIC ): # <channel> :<topic>
                parts = m.msg.split(":", 1)
                return parts[1] if len(parts) > 1 else "" # Return topic or empty string
            elif ( m.type == RPL_NOTOPIC ): # <channel> :No topic is set
                return False
                
            self.msgBuff.append( m )
        

    ####################################################################
    # Retrieves a nick list
    def retr_names(self, channel):
        """
        Sends a NAMES command to list users in a channel.

        This is typically an internal helper. `get_users()` is the public
        interface for fetching and returning the user list.

        Args:
            channel (str): The channel whose user list is to be retrieved.
        """
        self.sock.send(f"NAMES {channel}\r\n".encode('utf-8'))

    ####################################################################
    # Reads the nick list
    def get_users(self, channel):
        """
        Retrieves a list of users in the specified channel.

        Args:
            channel (str): The name of the channel.

        Returns:
            list: A list of user nicks (strings) in the channel.
        """
        self.retr_names( channel )
        
        data = []
        m = self.getmsg( True )
        
        while ( m.type != RPL_ENDOFNAMES ):
            if ( m.type == RPL_NAMEREPLY ): # = #channel :user1 @user2 +user3
                parts = m.msg.split(":", 1)
                if len(parts) > 1:
                    names_str = parts[1].strip()
                    if names_str: # Ensure not empty
                        data.extend(names_str.split()) # split() handles multiple spaces
            else:
                self.msgBuff.append( m )

            m = self.getmsg( True )

        return data

    ####################################################################
    # Retrieves a channel list
    def retr_channels(self):
        """
        Sends a LIST command to retrieve the list of channels.

        This is typically an internal helper. `get_channels()` is the public
        interface for fetching and returning the channel list.
        """
        self.sock.send( "LIST\r\n".encode('utf-8') )
            
    ####################################################################
    # Reads the channel list
    def get_channels(self):
        """
        Retrieves a list of public channels from the server.

        Returns:
            list: A list of tuples, where each tuple contains
                  (channel_name, user_count, topic).
        """
        self.retr_channels( )
        
        channels = []
        m = self.getmsg( True )
        
        while ( m.type != RPL_LISTEND ):
            if ( m.type == RPL_LISTSTART ): # Obsolete, but handle if received
                pass
            elif ( m.type == RPL_LIST ): # <channel> <# visible> :<topic>
                parts = m.msg.split(":", 1)
                info_fields = parts[0].strip().split(" ")
                if len(info_fields) >= 2: # channel, users_count
                    channel_name = info_fields[0]
                    users_count = info_fields[1]
                    topic = parts[1] if len(parts) > 1 else ""
                    channels.append((channel_name, users_count, topic))
            else:
                self.msgBuff.append( m )
                
            m = self.getmsg( True )
            
        return channels

    ####################################################################
    # Invites someone to a channel
    def invite(self, nick, channel):
        """
        Invites a user to a channel.

        Args:
            nick (str): The nickname of the user to invite.
            channel (str): The channel to invite the user to.
        """
        self.sock.send(f"INVITE {nick} {channel}\r\n".encode('utf-8'))

    ####################################################################
    # Removes a user from a channel
    def kick(self, channel, nick, comment=None):
        """
        Kicks a user from a channel.

        Requires appropriate channel privileges.

        Args:
            channel (str): The channel from which to kick the user.
            nick (str): The nickname of the user to kick.
            comment (str, optional): A comment for the kick. Defaults to None.
        """
        if comment is None:
            self.sock.send(f"KICK {channel} {nick}\r\n".encode('utf-8'))
        else:
            self.sock.send(f"KICK {channel} {nick} :{comment}\r\n".encode('utf-8'))

    ####################################################################
    # Quit the channel
    def quit_channel(self, channel):
        """
        Leaves (parts) a specified channel.

        Args:
            channel (str): The channel to leave.
        """
        self.sock.send(f"PART {channel}\r\n".encode('utf-8'))

    ####################################################################
    # Quit's the server
    def quit(self, msg="Client quit"):
        """
        Disconnects from the IRC server.

        Args:
            msg (str, optional): The quit message to send to the server.
                                 Defaults to "Client quit".
        """
        self.sock.send(f"QUIT :{msg}\r\n".encode('utf-8'))
        self.sock.close( )

    ####################################################################
    # Joins a channel
    def join(self, channel, passwd=None):
        """
        Joins a specified IRC channel.

        Args:
            channel (str): The name of the channel to join (e.g., "#channel").
            passwd (str, optional): The password for the channel, if required.
        """
        # Channel names starting with '&' are local to the server.
        # '#' are network-wide. Other prefixes might exist.
        # The core logic here is just to send the command.
        if passwd is None:
            self.sock.send(f"JOIN {channel}\r\n".encode('utf-8'))
        else:
            self.sock.send(f"JOIN {channel} {passwd}\r\n".encode('utf-8'))
            # Note: some servers might expect channel names for JOIN to not include the prefix
            # if it's a standard one like '#', but this client seems to expect full name.

    ####################################################################
    # Changes the nickname
    def change_nick(self, nick):
        """
        Changes the client's nickname.

        Args:
            nick (str): The new nickname.
        """
        self.nick = nick # Update internal nick tracking
        self.sock.send(f"NICK {nick}\r\n".encode('utf-8'))

    ####################################################################
    # Ask's for the MOTD
    def refresh_motd(self):
        """Sends a MOTD command to the server to refresh the Message of the Day."""
        self.sock.send( "MOTD\r\n".encode('utf-8') )

    ####################################################################
    # Receives a message (and transparently answers to server ping's)
    def getmsg(self, fresh=False):
        """
        Retrieves the next IRC message from the server or internal buffer.

        This method handles automatic PING replies and CTCP VERSION requests.
        It also stores incoming MOTD lines in `self.motd`.

        Args:
            fresh (bool, optional): If True, forces reading a new message from
                                    the socket, ignoring the buffer. Defaults to False.

        Returns:
            irc_msg: A parsed `irc_msg` object.
        
        Raises:
            socket.error: If there's an issue reading from the socket (e.g., connection closed).
        """
        if ( not fresh ) and ( len( self.msgBuff ) > 0 ):
            return self.msgBuff.pop( 0 )

        while ( True ):
            
            s = getline( self.sock ) # s is bytes, getline may raise socket.error
            if ( len( s ) > 3 ): # Check length before slicing
                if s.lower().startswith(b"ping"): # s is bytes, compare with bytes
                    self.pong( s ) # Pass bytes to pong
                    continue
               
            m = irc_msg( s ) # s is bytes, irc_msg handles decoding

            if ( "version" in  m.ctcp_msg.lower() ):
                self.sendVer( m.by )
                continue

            elif ( m.type == RPL_MOTD ):
                self.motd += m.msg + "\n"
                continue

            elif ( m.type == RPL_MOTDSTART ):
                self.motd = ""
                continue

            return m

    ####################################################################
    # Sends a message ( msg ) to a receiver ( to ), which can 
    # be a channel or a user
    def sendmsg(self, to, msg):
        """
        Sends a standard message (PRIVMSG) to a specified target (user or channel).

        Args:
            to (str): The recipient (nickname or channel name).
            msg (str): The message content to send.
        """
        self.sock.send(f"PRIVMSG {to} :{msg}\r\n".encode('utf-8'))

    ####################################################################
    # Same as sendmsg, but MUSTN'T be answered
    def notice(self, to, msg):
        """
        Sends a NOTICE to a specified target (user or channel).

        Notices are similar to PRIVMSGs but should not be automatically replied to.

        Args:
            to (str): The recipient (nickname or channel name).
            msg (str): The message content to send.
        """
        self.sock.send(f"NOTICE {to} :{msg}\r\n".encode('utf-8'))

    ####################################################################
    # Answers a ping
    def pong(self, ping_bytes):
        """
        Responds to a PING request from the server.

        Args:
            ping_bytes (bytes): The raw PING message received from the server
                                (e.g., b"PING :server_token").
        """
        # PING command is usually "PING :<some_token>" or "PING <some_token>"
        # We need to send back "PONG :<some_token>" or "PONG <some_token>"
        if ping_bytes.startswith(b"PING "):
            pong_payload = ping_bytes[5:] # Get the part after "PING " (e.g., b":server_token")
            self.sock.send(b"PONG " + pong_payload + b"\r\n")
        else: 
            # Fallback for unexpected PING format, though getmsg filters by startswith(b"ping")
            # This part might be unreachable if getmsg's PING check is strict.
            # Original code had `ping[4:]` which assumed "PING" without a space.
            # Modern PINGs usually have a space or colon after PING.
            # Sending the raw PING payload back is a common behavior if unsure.
            self.sock.send(b"PONG " + ping_bytes[4:] + b"\r\n")


    ####################################################################
    # Answers a version request
    def sendVer(self, by):
        """
        Responds to a CTCP VERSION request from a user.

        Args:
            by (str): The nickname of the user requesting the version.
        """
        # VERSION is a string, chr(1) makes it CTCP
        self.notice(by, f"{chr(1)}{VERSION}{chr(1)}")

    ####################################################################
    # Connecting to the server and login
    def connect_to_server(self, passwd=None, serverpasswd=None):
        """
        Establishes the connection to the IRC server and handles initial registration.

        This includes setting up the socket (with SSL if specified), connecting,
        sending PASS (if server password is provided), NICK, and USER commands.
        It then waits for the end of the MOTD or a welcome message.

        Args:
            passwd (str, optional): The user's NickServ password.
            serverpasswd (str, optional): The server's connection password.
        
        Raises:
            socket.error: If the connection fails.
        """
        self.sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        if self.use_ssl: # Use the instance variable
            self.sock = ssl.wrap_socket(self.sock)
        self.sock.connect((self.server, self.port)) # Can raise socket.error
        
        if serverpasswd is not None:
            self.sock.send(f"PASS {serverpasswd}\r\n".encode('utf-8'))
            
        self.change_nick(self.nick) # Sends NICK command
        
        # Initial message reading loop after connection often handles PINGs or server notices
        # before MOTD. getmsg() handles PINGs.
        # We need to wait for registration confirmation (e.g., RPL_WELCOME 001)
        # or RPL_ENDOFMOTD / ERR_NOMOTD before proceeding with identify.
        # The original code waited for RPL_ENDOFMOTD.
        
        # Send USER command
        self.sock.send(f"USER {self.username} 0 * :{self.fullname}\r\n".encode('utf-8'))
        # Note: username2 was used in original, standard USER is <user> <mode> <unused> :<realname>
        # Using '0 *' for mode and unused is common.

        # Wait for end of MOTD or specific welcome messages before trying to identify
        # This loop can be more robust by checking for specific RPL codes indicating successful registration
        m = self.getmsg()
        while m.type != RPL_ENDOFMOTD and m.type != ERR_NOMOTD:
            # Add specific checks for welcome messages if needed e.g. m.type == "001"
            if m.type == "001": # RPL_WELCOME, indicates successful registration
                break # Can proceed after this
            m = self.getmsg()
                    
        if passwd is not None:
            self.sendmsg("NickServ", f"IDENTIFY {passwd}")

    ####################################################################
    # Object constructor
    def __init__(self,
                 nick,
                 server,
                 port=6667,
                 ssl=False, # Parameter name for SSL usage
                 username="user",
                 username2="user", # Retained for potential use, though USER cmd is simplified
                 fullname="user Name",
                 serverpasswd=None,
                 passwd=None):
        """
        Initializes the IRC client.

        Sets up connection parameters (nick, server, port, SSL, credentials)
        and then calls `connect_to_server()` to establish the connection and register.

        Args:
            nick (str): The client's nickname.
            server (str): The IRC server address.
            port (int, optional): The server port. Defaults to 6667.
            ssl (bool, optional): Whether to use SSL for the connection. Defaults to False.
            username (str, optional): The username for the USER command. Defaults to "user".
            username2 (str, optional): Second username part, often unused or same as username.
                                     Retained from original, standard USER uses '0 *'. Defaults to "user".
            fullname (str, optional): The real name for the USER command. Defaults to "user Name".
            serverpasswd (str, optional): Password for server access (PASS command). Defaults to None.
            passwd (str, optional): Password for NickServ identification. Defaults to None.
        """
        self.nick = nick
        self.server = server
        self.port = port
        self.use_ssl = ssl # Store SSL preference
        self.username = username
        self.username2 = username2 # Stored, available if a different USER string format is needed.
        self.fullname = fullname
        self.connect_to_server( passwd, serverpasswd )
