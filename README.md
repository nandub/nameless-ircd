nameless-ircd
=============

Source code for nameless ircd

###useage###

binds to 127.0.0.1 by default

    python main.py --port 6667

for binding to a certain host, currently ipv4 only

    python main.py --port 6667 --host irc.server.tld
	

bind to all ipv4 interfaces

    python main.py --port 6667 --host 0.0.0.0
	
##setting up adminserv##

    add the public tripcode of the admin to ircd/admin.hash

    i.e. admin|SOMETRIPCODEHERE

    default is admin#admin

###adminserv commands###

   * list user - list users connected
   * list chan - list formed channels
   * count user - count users connected
   * count chan - count channels formed

   * kill [nickname] - kill a user's connection
   * nerf_all - set global +P for all users
   * denerf_all - unset global +P for all users
   * nerf [nickname] - lock +P on user
   * denerf [nickname] - unlock +P on user
   
   * flood interval [seconds] - set flood interval in seconds
   * flood bpi [number] - set how many bytes per interval sets of a floodkill
   * flood lpi [number] - set how many lines per interval sets of a floodkill
   
   * ping [seconds timeout max] - set ping timeout settings
   * global [message] - send global m
   * debug - toggle debug mode (see everything mode)essage


