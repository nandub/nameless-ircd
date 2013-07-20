nameless-ircd
=============

###What Is Nameless IRCD?###

Nameless IRCD is a 0 config easy to use and set up irc daemon with a twist.
There are no chan ops, no channel modes, no moderation mechanisms and no nicknames.
It's meant to be dead simple to set up, connect up and run new instances. 

###No Nicknames?###

Yes, instead nameless has 3 types of identities you can use all with thier own threat model

* Tripcode

Connects to the server with a nickname in the format nickname#secret

Their nickname is set to nickname|hash where the nickname and secret are digested through a 
hash function combined with a secret server salt, (see hash function at util._tripcode , needs auditing)

Uses channels with prefix # or &

* User ID

Connects to the server and their nickname is set to a random garble for each new connection

Uses channels with prefix # or &

* Nameless

Same as User ID but only uses channels with prefix &

###What are these & channels?###

Channels with the prefix & do not relay the nickname of the chatter or parts and joins.

![Sample Chatter in &public](https://github.com/majestrate/nameless-ircd/raw/master/nameless.png)

###What is URC?###

URC stands for URC relay chat, it's a variant of irc that requries no state, for more info see [here](http://anonet2.biz/URC)

###Threat model###

Communications Between Servers are plaintext with no authentication or authorization,
this means that PRIVMSG between Alice on leaf1 and Bob on leaf2 is 100% spoofable (use otr)

Server Opers can see and control everything on their own server, if you dislike a server oper,
run your own server and link it onto the URC chat Bus.

It's easy to flood the server to server medium and nameless ircd has some active flood protection
not every flood is stopable :p

###Setting up a Server###

**please note**

nameless-ircd only supports URC for inter-server communications at the moment

you can find a public list of these servers at http://anonet2.biz/

####Requirements####

* Python 3.2 or higher

#### Setup ####

python setup.py install

#### Usage ####

Super dead simple setup, will accept incomming connections at 127.0.0.1 port 6667 

    ircd.py --name irc.server.tld --host 127.0.0.1
	
To connect to that with your irc client do 

    /connect localhost

or

    /server localhost
	
depending on your client, if you want people to connect via the internet (not recommended):

change 

    --host 127.0.0.1 

to 

    --host 0.0.0.0

and port forward so that port 6667 is accessable from outside your router.

SSL is currently **NOT** supported so hosting the server on tor hidden services or i2p is *highly* recommended 

###More Setup Options###

Accept no incomming connections use default irc port (6667) call the server "irc.server.tld" and Bind to 0.0.0.0

    ircd.py --name irc.sever.tld --no-link --host 0.0.0.0
	
Allow others to link up to you at via 127.0.0.1 port 6660

    ircd.py --name irc.server.tld --link-port 6660

... Or allow from anywhere
    
    ircd.py --name irc.server.tld --link-port 6660 --link-host 0.0.0.0
	
... or use ipv6 loopback

    ircd.py --name irc.server.tld --link-port 6660 --link-host ::1 -6
	
Connect up to another server at some.onion port 6660 with no incomming connections allowed

    # currently assumes tor socks is at 127.0.0.1 port 9050
	
    ircd.py --name irc.server.tld --onion-urc some.onion --no-link

Connect up to a remote server at irc.something.org port 6660 using ipv6 and allow incomming connetions from ::1 port 6660

    ircd.py -6 --name irc.server.tld --remote-urc irc.something.org --link-port 6660 --link-host ::1

# TODO #

* Make server more compliant to the IRC protocol
* Document Codebase more
* Find and Fix bugs
* Code Audit
