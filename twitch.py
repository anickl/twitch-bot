#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
@author: Erik Sandberg
https://github.com/317070/python-twitch-stream/blob/master/examples/basic_chat.py
https://www.elifulkerson.com/projects/commandline-text-to-speech.php # Voice.exe for windows TTS
Adapted from code with the following license:
    
Copyright (c) 2015 Jonas Degrave
Permission is hereby granted, free of charge, to any person obtaining a copy of this software and associated documentation files (the "Software"), to deal in the Software without restriction, including without limitation the rights to use, copy, modify, merge, publish, distribute, sublicense, and/or sell copies of the Software, and to permit persons to whom the Software is furnished to do so, subject to the following conditions:
The above copyright notice and this permission notice shall be included in all copies or substantial portions of the Software.
THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY, FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM, OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN THE SOFTWARE.
TWITCH USERNAME: ImABotBoy
TWITCH PW: BotBoyBaby
NICK = "ImABotBoy"
PASS = "oauth:1ruvijtcfg81i6d0b44j5ct76mrhyo"
This file contains the python code used to interface with the Twitch
chat. Twitch chat is IRC-based, so it is basically an IRC-bot, but with
special features for Twitch, such as congestion control built in.
"""
import pyHook #import HookManager, GetKeyState, HookConstants
#from __future__ import print_function
import tkinter as tk
import time
import socket
import re
import sys
try: # Mac user
    import fcntl
except: # Windows user, they'll use socket instead
    pass
import subprocess
import os
import errno
import threading
from PIL import Image,ImageTk
import numpy as np
class TwitchChatStream(object):
    """
    The TwitchChatStream is used for interfacing with the Twitch chat of
    a channel. To use this, an oauth-account (of the user chatting)
    should be created. At the moment of writing, this can be done here:
    https://twitchapps.com/tmi/
    :param username: Twitch username
    :type username: string
    :param oauth: oauth for logging in (see https://twitchapps.com/tmi/)
    :type oauth: string
    :param verbose: show all stream messages on stdout (for debugging)
    :type verbose: boolean
    """

    def __init__(self, username, oauth, verbose=False):
        """Create a new stream object, and try to connect."""
        self.username = username
        self.oauth = oauth
        self.verbose = verbose
        self.current_channel = ""
        self.last_sent_time = time.time()
        self.buffer = []
        self.connected = False
        self.s = None

    def __enter__(self):
        self.connect()
        return self

    def __exit__(self, type, value, traceback):
        self.s.close()

    @staticmethod
    def _logged_in_successful(data):
        """
        Test the login status from the returned communication of the
        server.
        :param data: bytes received from server during login
        :type data: list of bytes
        :return boolean, True when you are logged in.
        """
        '''
        if re.match(r'^:(testserver\.local|tmi\.twitch\.tv)'join(self
                    r' NOTICE \* :'
                    r'(Login unsuccessful|Error logging in)*$',
                    data.strip()):
            return False'''
        if "Login authentication failed" in data or "Improperly formatted auth" in data:
            return False
        else:
            return True

    @staticmethod
    def _check_has_ping(data):
        """
        Check if the data from the server contains a request to ping.
        :param data: the byte string from the server
        :type data: list of bytes
        :return: True when there is a request to ping, False otherwise
        """
        return re.match(
            r'^PING :tmi\.twitch\.tv$', data)

    @staticmethod
    def _check_has_channel(data):
        """
        Check if the data from the server contains a channel switch.
        :param data: the byte string from the server
        :type data: list of bytes
        :return: Name of channel when new channel, False otherwise
        """
        return re.findall(
            r'^:[a-zA-Z0-9_]+\![a-zA-Z0-9_]+@[a-zA-Z0-9_]+'
            r'\.tmi\.twitch\.tv '
            r'JOIN #([a-zA-Z0-9_]+)$', data)

    @staticmethod
    def _check_has_message(data):
        """
        Check if the data from the server contains a message a user
        typed in the chat.
        :param data: the byte string from the server
        :type data: list of bytes
        :return: returns iterator over these messages
        """
        return re.match(r'^:[a-zA-Z0-9_]+\![a-zA-Z0-9_]+@[a-zA-Z0-9_]+'
                        r'\.tmi\.twitch\.tv '
                        r'PRIVMSG #[a-zA-Z0-9_]+ :.+$', data)

    def connect(self):
        """
        Connect to Twitch
        """

        # Do not use non-blocking stream, they are not reliably
        # non-blocking
        # s.setblocking(False)
        # s.settimeout(1.0)

        s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        connect_host = "irc.twitch.tv"
        connect_port = 6667
        try:
            s.connect((connect_host, connect_port))
        except (Exception, IOError):
            print ("Unable to create a socket to %s:%s" % (connect_host,connect_port))
            raise  # unexpected, because it is a blocking socket

        # Connected to twitch
        # Sending our details to twitch...
        s.send(('PASS %s\r\n' % self.oauth).encode('utf-8'))
        s.send(('NICK %s\r\n' % self.username).encode('utf-8'))
        if self.verbose:
            print ('PASS %s\r\n' % self.oauth)
            print ('NICK %s\r\n' % self.username)

        received = s.recv(1024).decode()
        if self.verbose:
            print (received)
        if not TwitchChatStream._logged_in_successful(received):
            # ... and they didn't accept our details
            self.connected=False
            return #raise IOError("Twitch did not accept the username-oauth combination")
        
        else:
            self.connected=True
            # ... and they accepted our details
            # Connected to twitch.tv!
            # now make this socket non-blocking on the OS-level
            try: # Mac user
                fcntl.fcntl(s,fcntl.F_SETFL,os.O_NONBLOCK)
            except: # Windows user
                s.setblocking(0)
            self.s = s


    def _push_from_buffer(self):
        """
        Push a message on the stack to the IRC stream.
        This is necessary to avoid Twitch overflow control.
        """
        if len(self.buffer) > 0:
            if time.time() - self.last_sent_time > 5:
                try:
                    message = self.buffer.pop(0)
                    self.s.send(message.encode('utf-8'))
                    if self.verbose:
                        print (message)
                finally:
                    self.last_sent_time = time.time()

    def _send(self, message):
        """
        Send a message to the IRC stream
        :param message: the message to be sent.
        :type message: string
        """
        if len(message) > 0:
            self.buffer.append(message + "\n")

    def _send_pong(self):
        """
        Send a pong message, usually in reply to a received ping message
        """
        self._send("PONG")

    def join_channel(self, channel):
        """
        Join a different chat channel on Twitch.
        Note, this function returns immediately, but the switch might
        take a moment
        :param channel: name of the channel (without #)
        """
        self.s.send(('JOIN #%s\r\n' % channel).encode('utf-8'))
        if self.verbose:
            print ('JOIN #%s\r\n' % channel)

    def send_chat_message(self, toChannel, message):
        """
        Send a chat message to the server.
        :param message: String to send (don't use \\n)
        :param toChannel: lowercase string of channel name to send message to
        """
        self._send("PRIVMSG #{0} :{1}".format(toChannel, message))

    def _parse_message(self, data):
        """
        Parse the bytes received from the socket.
        :param data: the bytes received from the socket
        :return:
        """
        if TwitchChatStream._check_has_ping(data):
            self._send_pong()
        if TwitchChatStream._check_has_channel(data):
            self.current_channel = \
                TwitchChatStream._check_has_channel(data)[0]

        if TwitchChatStream._check_has_message(data):
            return {
                'channel': re.findall(r'^:.+![a-zA-Z0-9_]+'
                                      r'@[a-zA-Z0-9_]+'
                                      r'.+ '
                                      r'PRIVMSG (.*?) :',
                                      data)[0],
                'username': re.findall(r'^:([a-zA-Z0-9_]+)!', data)[0],
                'message': re.findall(r'PRIVMSG #[a-zA-Z0-9_]+ :(.+)',
                                      data)[0]#.decode('utf8')
            }
        else:
            return None

    def twitch_receive_messages(self):
        """
        Call this function to process everything received by the socket
        This needs to be called frequently enough (~10s) Twitch logs off
        users not replying to ping commands.
        :return: list of chat messages received. Each message is a dict
            with the keys ['channel', 'username', 'message']
        """
        self._push_from_buffer()
        result = []
        while True:
            # process the complete buffer, until no data is left no more
            try:
                msg = self.s.recv(4096).decode()     # NON-BLOCKING RECEIVE!
            except socket.error as e:
                err = e.args[0]
                if err == errno.EAGAIN or err == errno.EWOULDBLOCK:
                    # There is no more data available to read
                    return result
                else:
                    # a "real" error occurred
                    # import traceback
                    # import sys
                    # print(traceback.format_exc())
                    # print("Trying to recover...")
                    self.connect()
                    return result
            else:
                if self.verbose:
                    print (msg)
                rec = [self._parse_message(line)
                       for line in filter(None, msg.split('\r\n'))]
                rec = [r for r in rec if r]     # remove Nones
                result.extend(rec)


class Interface(tk.Tk):
    def __init__(self):
        tk.Tk.__init__(self)
        self.credentialsFrame = tk.LabelFrame(self,text="Login Credentials",padx=3)
        self.channelFrame = tk.LabelFrame(self,text="Channel")
        self.imageFrame = tk.LabelFrame(self,text="Image Options")
        self.menubar = tk.Menu(self,tearoff=0)
        self.menubar.add_command(label="Help",command = self.showHelp)
        self.config(menu=self.menubar)
        
        self.isInChannel = False
        self.wantsToReceive = False
        self.receiving = False
        self.STOP = False
        self.lastMessageTime = time.time()
        self.title("Twitch Colors")
        self.attributes('-topmost',1)
        self.lift()
        self.focus_force()
        self.width=0
        self.height=0
        self.array=np.zeros((0,0))
        self.imTop=0
        OS = os.name
        if OS == 'nt': # Windows
            self.isWindows = True
        else:
            self.isWindows = False
            
        self.PASS = ""
        self.NICK = ""
        
        # Credentials Frame
        self.NICKLabel = tk.Label(self.credentialsFrame,text="Username")
        self.NICKLabel.grid(row=0,column=0,columnspan=2)
        self.NICKEntry = tk.Entry(self.credentialsFrame,width=30)
        self.NICKEntry.grid(row=1,column=0,columnspan=2,padx=10,pady=5)

        self.PASSLabel = tk.Label(self.credentialsFrame,text="OAuth Code")
        self.PASSLabel.grid(row=0,column=2)
        self.PASSEntry = tk.Entry(self.credentialsFrame,width=30, show="*")
        self.PASSEntry.grid(row=1,column=2,padx=5,pady=5)
                
        self.NICKEntry.insert(0,"UserNameHere")
        self.PASSEntry.insert(0,"oauth:exampleabcdefg12345677")
        #self.NICKEntry.insert(0,"ImABotBoy")
        #self.PASSEntry.insert(0,"oauth:1ruvijtcfg81i6d0b44j5ct76mrhyo")
        
        self.connectButton = tk.Button(self.credentialsFrame,text="Connect to Twitch", command=self.connect,padx=38)
        self.connectButton.grid(row=2,column=2,padx=7,pady=5)

        # Channel Frame        
        self.JOINLabel = tk.Label(self.channelFrame,text="Channel Name")
        self.JOINLabel.grid(row=0,column=0,columnspan=2,padx=5,pady=5)
        self.JOINEntry = tk.Entry(self.channelFrame,width=30)
        self.JOINEntry.grid(row=1,column=0,columnspan=2,padx=5,pady=5)
        self.JOINEntry.insert(0,"djskiskyskoski")
        
        self.joinButton = tk.Button(self.channelFrame,text="Join Channel",command = self.join,padx=55)
        self.joinButton.grid(row=1,column=2,pady=5,padx=5)
        self.joinButton.config(state='disabled')

        
        self.receiveMessagesButton = tk.Button(self.channelFrame,text="Read Chat!",command=self.receiveMessages,padx=60)
        self.receiveMessagesButton.grid(row=2,column=0,columnspan=2,pady=5,padx=5)
        self.attributes('-topmost',0)
        
        self.stopButton = tk.Button(self.channelFrame,text="Stop Reading", command = self.stop,padx=54)
        self.stopButton.grid(row=2,column=2,columnspan=2,padx=5,pady=5)
        
        #Image Frame
        self.wLabel = tk.Label(self.imageFrame,text="width")
        self.wLabel.grid(row=0,column=0,columnspan=2,padx=5,pady=5)
        self.hLabel = tk.Label(self.imageFrame,text="height")
        self.hLabel.grid(row=0,column=2,columnspan=2,padx=5,pady=5)

        self.wEntry = tk.Entry(self.imageFrame,width = 30)
        self.wEntry.grid(row=1,column=0,columnspan=2,padx=5,pady=5)
        self.hEntry = tk.Entry(self.imageFrame, width = 30)
        self.hEntry.grid(row=1,column=2,columnspan=2,padx=5,pady=5)

        self.colBool=tk.IntVar()
        self.emoBool=tk.IntVar()
        self.checkColor = tk.Checkbutton(self.imageFrame, text='pixels',variable=self.colBool)
        self.checkEmote = tk.Checkbutton(self.imageFrame, text='emotes',variable=self.emoBool)
        self.checkColor.grid(row=0,column=4,padx=5,pady=5)
        self.checkEmote.grid(row=1,column=4,padx=5,pady=5)

        self.imageButton = tk.Button(self.imageFrame,text='launch image',command=self.launchImage,padx=5)
        self.imageButton.grid(row=1,column=5,padx=5,pady=5)
        # Grid Frames        
        self.credentialsFrame.grid(row=1,column=0,columnspan=2,padx=5,pady=5)
        self.channelFrame.grid(row=3,column=0,padx=5,pady=5,rowspan=2)
        self.imageFrame.grid(row=5,column=0,padx=5,pady=5,columnspan=2)
        self.closeButton = tk.Button(self,text="Close Program",command = self.totalDestroy)
        self.closeButton.grid(row=6,column=3,sticky='e',pady=5,padx=5)
        self.addButtons()
        self.disableButtons()

    def addButtons(self):
        self.allButtons = []
        self.allButtons.append(self.receiveMessagesButton)   
        self.allButtons.append(self.stopButton)
        
        
    def showHelp(self):
        top = tk.Toplevel(self)
        helpMessage  = "1. Obtain an 'OAuth' code from https://twitchapps.com/tmi/ to use along with your Twitch username.\n\n"
        helpMessage += "2. Connect to a channel once logged into Twitch and interact with messages via the buttons in the 'Channel' section.\n\n"
        topLabel = tk.Label(top,text=helpMessage)
        topLabel.pack()
        
    def launchImage(self):
        self.width=int(self.wEntry.get())
        self.height=int(self.hEntry.get())
        self.array=np.zeros((self.width,self.height))
        self.imTop=tk.Toplevel(self)
        self.topCanvas = tk.Canvas(self.imTop,width=self.width,height=self.height)
        self.topCanvas.pack(expand=tk.YES, fill=tk.BOTH)
        imOut=Image.fromarray(np.uint8(self.array)).convert('RGB')
        imOut.save('out.png')
        img = ImageTk.PhotoImage(Image.open("out.png"))  
        self.Im=self.topCanvas.create_image(0, 0, image=img)
        print(self.width)
        print(self.height)
        print(self.array.shape)
        print(self.Im)
         

    def updateIm(self):
        
        imOut=Image.fromarray(np.uint8(self.array)).convert('RGB')
        imOut.save('out.png')
        img = ImageTk.PhotoImage(Image.open("out.png"))  
        self.topCanvas.itemconfig(self.Im,image=img)
        print('update')
    
    def connect(self):
        self.NICK = self.NICKEntry.get()
        self.PASS = self.PASSEntry.get()
        if not self.PASS.startswith('oauth:'):
            self.PASS = 'oauth:'+self.PASS
        self.main = TwitchChatStream(self.NICK,self.PASS,verbose=False)
        #self.main = TwitchChatStream(self.NICK,self.PASS,verbose=True)
        self.main.connect()
        if self.main.connected:
            self.connectButton.config(bg="green")
            self.joinButton.config(state='normal')
            self.checkIfWantsToReceive()
            print("Connected")
        else:
            self.connectButton.config(bg="red")
            print("Connection failed")
            
    def join(self):
        self.joinButton.configure(bg="red")
        channel = self.JOINEntry.get().lower()
        self.main.join_channel(channel)
        #self.main.twitch_receive_messages()
        self.old_channel = self.main.current_channel
        time.sleep(1)
        self.main.twitch_receive_messages()
        print("-----------------")
        print("I was in: " + self.old_channel)
        print("I'm in channel: " + self.main.current_channel)
        print("-----------------")      
        if self.old_channel == self.main.current_channel:
            # Didn't actually join channel
            self.joinButton.configure(bg="red")
            self.disableButtons()
            print("I'm in channel: " + self.main.current_channel)
            
        else:
            # Successfully joined channel
            self.joinButton.configure(bg="green")
            self.enableButtons()
            self.isInChannel = True
        print("I'm in channel: " + self.main.current_channel)

                
    def resourcePath(self,filename):
        try:
            # PyInstaller creates a temp folder and stores path in _MEIPASS
            base_path = sys._MEIPASS
        except Exception:
            base_path = os.path.abspath(".")
        return os.path.join(base_path, filename)


            
    def receiveMessages(self):
        print("Receiving: ", self.receiving)
        self.STOP = False
        if not self.receiving and self.isInChannel:
            self.recThread = threading.Thread(target=self.receive)
            self.recThread.start()
            self.receiveMessagesButton.config(bg="green")
            print("After started thread and color changed to green")
        
    def stop(self):
        if self.isInChannel:
            try:            
                print("Wanted to receive before stopping? --> ", self.wantsToReceive)
                self.STOP = True    
                self.receiving = False
                self.wantsToReceive = False
                del(self.recThread) 
                self.receiveMessagesButton.config(bg="red")
            except Exception as e:
                print("GOT AN ERROR IN STOP: ", e)
                pass
        
    def totalDestroy(self):
        self.stop()
        self.destroy()        
        try:
            self.main.s.close()
        except:
            pass
        

            
    def checkIfWantsToReceive(self):
        if self.wantsToReceive and not self.receiving:
            print("USER HOTKEYED RECEIVED")
            self.receiveMessages()
        self.after(1000,self.checkIfWantsToReceive) # Call this function repeatedly every 1000 milliseconds
            



    def receive(self):
        print("IN RECEIVE FUNC")
        self.receiving = True
        
        if self.STOP:
            print ("self.stop is True")
            return
        
        
        
        
        while not self.STOP:
            #print(self.filterAt.get())
            rec = self.main.twitch_receive_messages()
            if rec and not self.STOP:
                for message_info in rec:
                    if message_info['channel'] == "#"+self.main.current_channel:
                        if self.STOP:
                            return  
                        user = message_info['username'].lower()
                        message = message_info['message']
                        print(message)
                        if(self.imTop!=0):
                            if(self.colBool.get()==1):
                                s=message.split()
                                for i in range(len(s)):
                                    j=s[i][0]
                                    if(j=='(' or j=='[' or j=='{'):
                                        k=s[i].split(',')
                                        if(len(k)==2):
                                            k[0]=int(k[0][1:])
                                            k[1]=int(k[1][:-1])
                                            self.array[k[0]][k[1]]=255
                                            self.updateIm()

                            if(self.emoBool.get()==1):
                                s=string.split()
                                for i in range(len(s)):
                                    j=s[i][0]
                                    if(j=='(' or j=='[' or j=='{'):
                                        k=s[i].split(',')
                                        if(len(k)==2):
                                            k[0]=k[0][1:]
                                            k[1]=k[1][:-1]
                                            self.updateIm()
                        
        
            time.sleep(.2)      

        self.STOP = False
                
    def enableButtons(self):
        for button in self.allButtons:
            button.config(state='normal')
    def disableButtons(self):
        for button in self.allButtons:
            button.config(state='disabled')
   
# ---------------------------------- #
# ---------- Run Program ----------- #


gui = Interface()

hm = pyHook.HookManager()    

# set the hook
gui.mainloop()
