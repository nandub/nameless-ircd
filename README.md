nameless-ircd
=============

Source code for nameless ircd

###useage###

binds to 127.0.0.1 by default

    python main.py --port 6667

for binding to a certain host, currently ipv4 only

    python main.py --port 6666 --host irc.server.tld
	
	
##setting up adminserv##

    add the public tripcode of the admin to ircd/admin.hash

    i.e. admin|SOMETRIPCODEHERE

###adminserv commands###

   * auth - attempt to authenticate as admin, connection will be killed on failure, this is the first command that needs to be issued per connection
   * list - list all connections
   * debug - toggle debug mode (see everything mode)
   * count - display number of open connections
   * kline [nickname] - kline a user by nickname
   * nerf - set global +P for all new users
   * die - kill server after 5 seconds
   * ping [seconds timeout max] - set ping timeout settings
   * global [message] - send global message
