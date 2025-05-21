#!/usr/bin/env python
# -*- encoding: utf-8 -*-
# PyIC example

from pyic import *
import logging

# Configure logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')

botName = "HelloBot" # NickName

server = "irc.freenode.net" # IRC server
channel = "#bot_testing" # IRC channel
greet = "Hello"
topic = "PyIC testing"

logging.info("Connecting...")

irc = irc_client( botName, server ) # Connect

logging.info("Message of the day:")
logging.info(irc.get_motd( ))

logging.info("Reading channel list")
logging.info(f"{len(irc.get_channels())} channels")


logging.info(f"Joining {channel}")
irc.join( channel ) # Joins the channel

irc.notice( channel, greet + " " + channel ) # talks to the channel
# use notice in order to avoid automatic responses

# Reads the user list
for usr in irc.get_users( channel ):
    
    
    logging.info(f'"{usr}" data')
    
    logging.info(irc.whois( clean_usr( usr ) )) # Shows the user data
    
    irc.notice( channel, greet + " " + usr ) # talks to the user


logging.info("Setting channel topic")
irc.set_topic( channel, topic )

logging.info(f"Topic: {irc.get_topic( channel )}")

logging.info("Waiting for users...")
# Greets who enters the channel
while ( True ):
    
    msg = irc.getmsg( )
    
    if ( msg.type.upper( ) == "JOIN" ): # Someone entered the channel
    
        if ( msg.by != botName ):

            logging.info(f"'{msg.by}' has arrived")
            irc.notice( channel, greet + " " + msg.by )
            logging.info(irc.whois( msg.by ))
