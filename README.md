# PyIC - Python IRC Client Library

PyIC is a Python library for interacting with IRC servers, providing functionalities for connecting, sending/receiving messages, handling users and channels, and basic DCC support. This version has been modernized for Python 3.

## Features

*   Connect to IRC servers (with optional SSL).
*   Join/part channels, send/receive messages (PRIVMSG, NOTICE).
*   Basic IRC commands: NICK, QUIT, TOPIC, WHOIS, WHOWAS, NAMES, LIST, MODE, KICK, INVITE.
*   Parse incoming IRC messages into an easy-to-use `irc_msg` object.
*   Basic DCC SEND/TSEND offer parsing and download handling (`dcc_download` thread).
*   Automatic PING replies and CTCP VERSION replies.
*   Uses the `logging` module for output; configurable by the application.
*   Python 3 compatible.

## Status/Disclaimer

This library was originally written by kenkeiras in 2010 and has been modernized to support Python 3 and incorporate some updated practices. It provides a foundational set of IRC client functionalities.

## Installation

To use PyIC, simply include the `pyic.py`, `irc_msg.py`, `dcc.py`, and `irc_codes.py` files in your Python project's directory or ensure they are in your `PYTHONPATH`.

## Quick Start

Here's a short example demonstrating how to connect to an IRC server, join a channel, send a message, and receive messages:

```python
import logging
import socket # For handling socket errors
from pyic import irc_client, clean_usr # Import necessary components
from irc_codes import DCC_SEND_OFFER, RPL_WELCOME # Example specific codes
from dcc import dcc_download # For DCC downloads

# Basic logging configuration
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')

# IRC Configuration
server = "irc.libera.chat" # Replace with your server
port = 6697 # Standard SSL port, use 6667 for non-SSL
use_ssl = True
nickname = "PyICBot"
channel_to_join = "#pyic_testing"

try:
    # Initialize and connect
    logging.info(f"Connecting to {server}:{port} as {nickname}...")
    irc = irc_client(
        nickname, 
        server, 
        port=port, 
        ssl=use_ssl, 
        fullname="PyIC Test Bot",
        username="pyicbot",
    )
    logging.info("Connected successfully.")

    # Join a channel
    logging.info(f"Joining channel {channel_to_join}...")
    irc.join(channel_to_join)
    logging.info(f"Joined {channel_to_join}.")

    irc.sendmsg(channel_to_join, "Hello from PyIC!")

    # Simple message receiving loop
    logging.info("Listening for messages...")
    for _ in range(10): # Loop a few times for demonstration
        msg = irc.getmsg() 
        
        logging.info(f"RAW: {msg.raw}")

        if msg.type == "PRIVMSG":
            logging.info(f"<{msg.by}> to {msg.to}: {msg.msg}")
            if msg.msg.strip() == "!hello":
                irc.sendmsg(msg.to if msg.to != nickname else msg.by, f"Hello {msg.by}!")
        elif msg.type == "JOIN":
            logging.info(f"{msg.by} joined {msg.to}")
        elif msg.type == DCC_SEND_OFFER:
            logging.info(f"DCC Offer from {msg.by}: File='{msg.file}', IP={msg.ip}, Port={msg.port}, Size={msg.size}")
        elif msg.type == RPL_WELCOME:
             logging.info(f"Welcome to the server: {msg.msg}")
        # Add more elif blocks here for other message types you want to handle

    irc.quit("PyIC bot signing off.")
    logging.info("Disconnected.")

except socket.error as e:
    logging.error(f"Socket error: {e}")
except Exception as e:
    logging.error(f"An unexpected error occurred: {e}", exc_info=True)

```

## Core Components Overview

*   **`irc_client` (in `pyic.py`):** The main class for IRC interaction. It handles establishing the connection (including SSL), sending commands to the server, receiving messages, and provides methods for common IRC operations.
    *   **Note on CTCP VERSION:** The library automatically responds to CTCP VERSION requests using the `VERSION` string defined at the top of `pyic.py`.
*   **`irc_msg` (in `irc_msg.py`):** Represents a parsed IRC message received from the server. After a raw line is fetched by `irc_client.getmsg()`, it's parsed into an `irc_msg` object. Key attributes include:
    *   `raw_bytes` (bytes): The original raw byte string.
    *   `raw` (str): The UTF-8 decoded string of the raw message.
    *   `by` (str): Sender's nickname.
    *   `origin` (str): Sender's full origin (e.g., `user@host`).
    *   `type` (str): The IRC command or numeric reply (e.g., "PRIVMSG", "JOIN", "372").
    *   `to` (str): The target of the message (e.g., a channel or your nick).
    *   `msg` (str): The actual message content or parameters of a command.
    *   `ctcp` (bool): True if the message is a CTCP message.
    *   `ctcp_msg` (str): The content of the CTCP message.
    *   If `type == DCC_SEND_OFFER` (constant from `irc_codes.py`), DCC-related attributes are populated: `file`, `ip`, `port`, `size`, `turbo`.
*   **`dcc_download` (in `dcc.py`):** A `threading.Thread` subclass for handling DCC file downloads. It takes an `irc_msg` object (which contains a DCC offer) and manages the download in a separate thread.
*   **`irc_codes.py`:** Contains constants for many standard IRC RPL_ (reply) and ERR_ (error) numeric codes, making it easier to check message types (e.g., `RPL_WELCOME`, `ERR_NOSUCHNICK`, `DCC_SEND_OFFER`).

### Handling Different Message Types

The core of an IRC bot involves a loop that fetches messages and then acts based on the message `type` or content. Here's a more detailed example:

```python
# Assuming 'irc' is a connected irc_client instance and in your main loop:
# from irc_codes import RPL_WELCOME, RPL_TOPIC, DCC_SEND_OFFER, ERR_NOSUCHNICK 
# (import other RPL_ and ERR_ codes as needed)

# msg = irc.getmsg() # Fetch a message
# logging.info(f"RECV: {msg.raw}") # Log the raw message line for debugging

# if msg.type == "PRIVMSG":
#     logging.info(f"Private message from {msg.by} to {msg.to}: {msg.msg}")
#     if "hello" in msg.msg.lower():
#         # Respond to user if PM, or to channel if channel message
#         recipient = msg.by if msg.to == irc.nick else msg.to
#         irc.sendmsg(recipient, f"Hello {msg.by}!")
# elif msg.type == "NOTICE":
#     logging.info(f"Notice from {msg.by} to {msg.to}: {msg.msg}")
# elif msg.type == "JOIN":
#     logging.info(f"{msg.by} joined channel {msg.to}")
#     if msg.by != irc.nick: # Don't greet self
#         irc.sendmsg(msg.to, f"Welcome {msg.by}!")
# elif msg.type == "PART":
#     logging.info(f"{msg.by} left channel {msg.to} (Reason: {msg.msg})")
# elif msg.type == RPL_WELCOME: # Typically "001"
#     logging.info(f"Welcome to the server: {msg.msg}")
# elif msg.type == RPL_TOPIC: # Typically "332"
#     logging.info(f"Topic for channel {msg.to}: {msg.msg}")
# elif msg.type == DCC_SEND_OFFER:
#     logging.info(f"DCC SEND Offer from {msg.by}: File='{msg.file}', IP={msg.ip}, Port={msg.port}, Size={msg.size}, Turbo={msg.turbo}")
#     # Example: Accept DCC (ensure you have dcc_download imported)
#     # dl = dcc_download(msg, func=lambda: logging.info(f"DCC for {msg.file} finished."))
#     # dl.start()
# # Handle a specific error reply
# elif msg.type == ERR_NOSUCHNICK: # Typically "401"
#     logging.warning(f"Attempted action on non-existent nick/channel: {msg.msg}")

# # CTCP Handling (example for CTCP PING, note: CTCP VERSION is auto-handled by pyic.py)
# if msg.ctcp:
#     logging.info(f"Received CTCP {msg.ctcp_msg} from {msg.by}. Full CTCP: {msg.msg}")
#     if msg.ctcp_msg.upper().startswith("PING"):
#         # Extract the timestamp or payload from the CTCP PING
#         ping_payload = msg.ctcp_msg[len("PING"):].strip()
#         logging.info(f"Responding to CTCP PING from {msg.by} with payload '{ping_payload}'")
#         irc.notice(msg.by, f"{chr(1)}PING {ping_payload}{chr(1)}")
```
Remember to import necessary `RPL_` and `ERR_` constants from `irc_codes.py`, or use their string numeric values directly.

### Handling Server Errors/Replies

Many IRC operations, if they fail or have specific responses, will result in numeric reply codes from the server (rather than Python exceptions from this library). These are found in `msg.type`. For example:
*   `ERR_NOSUCHNICK ("401")`: Attempting an action on a nickname that doesn't exist.
*   `ERR_NOSUCHCHANNEL ("403")`: Attempting to join a channel that doesn't exist or has modes preventing entry.
*   `ERR_CANNOTSENDTOCHAN ("404")`: Cannot send to channel because you're not in it or it's moderated (+m).
*   `ERR_NICKNAMEINUSE ("433")`: The nickname you're trying to use is already taken.

Your application should check `msg.type` for these codes if you need to handle such conditions explicitly.
```python
# Example: After trying to send a message to a user who might not exist
# (This check would be in your message loop after receiving the server's response)
# if msg.type == ERR_NOSUCHNICK: # ERR_NOSUCHNICK needs to be imported or defined
#     logging.warning(f"Failed to send message or perform action, target does not exist: {msg.msg}")
```

## Common Operations (Brief Code Snippets)

```python
# Assuming 'irc' is an initialized and connected irc_client instance

# Changing Nick
irc.change_nick("NewPyICNick")

# Sending a private message to a user
irc.sendmsg("AnotherUser", "Hello there!")

# Sending a notice
irc.notice("AnotherUser", "This is a notice.")

# Getting WHOIS information
user_data = irc.whois("SomeUser")
if user_data:
    logging.info(f"WHOIS info for SomeUser: {user_data}")

# Listing users in a channel
users_in_channel = irc.get_users("#some_channel")
logging.info(f"Users in #some_channel: {users_in_channel}")

# Listing available channels (can be very long)
# Note: This can be a very large list on big servers and take time.
# channels_list = irc.get_channels() 
# for channel_name, user_count, topic_str in channels_list: # Each item is a tuple
#     logging.info(f"Channel: {channel_name}, Users: {user_count}, Topic: {topic_str}")

# Checking for DCC Offer and starting a download
# (Typically within your message processing loop after msg = irc.getmsg())
# from irc_codes import DCC_SEND_OFFER 
# from dcc import dcc_download

# if msg.type == DCC_SEND_OFFER:
#     logging.info(f"DCC Offer from {msg.by}: File='{msg.file}', IP={msg.ip}, Port={msg.port}, Size={msg.size}, Turbo={msg.turbo}")
#     
#     # Example: Define a callback for when download finishes
#     def dcc_done():
#         logging.info(f"DCC download of {msg.file} finished (or failed).")
#
#     # To start download:
#     logging.info(f"Starting download of {msg.file}...")
#     dl_thread = dcc_download(msg, func=dcc_done) # msg is the irc_msg object
#     dl_thread.start()
```

## Logging

PyIC uses the Python `logging` module for its internal messages and error reporting. Library components (`pyic.py`, `irc_msg.py`, `dcc.py`) create loggers using their module names (e.g., `logging.getLogger('pyic')`, `logging.getLogger('irc_msg')`).

Applications using PyIC can configure the root logger or these specific loggers to control the output level (e.g., `INFO`, `DEBUG`, `ERROR`) and set up handlers (e.g., to log to a file or console with specific formatting). The Quick Start section shows a basic console logging setup:
```python
import logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
```
For more advanced logging configurations, refer to the official Python `logging` documentation.

## License

PyIC is licensed under the GNU General Public License v3.0 or later. See the `LICENSE` file (not provided in this project, but typically you would include one) or the GPLv3 text for details. The original license of PyIC was GPLv3 or later.
```
