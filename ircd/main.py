#!/usr/bin/env python
from nameless import server, user, adminserv, util, s2s, torchat
import signal, traceback, asyncore, json, sys
from threading import Thread

serv = None
def hup(sig,frame):
    '''
    called on SIGHUP
    '''
    print ('reload')
    try:
        global serv
        serv.reload()
    except:
        print ('Error reloading')
        print (traceback.format_exc())
    else:
        print ('okay')

def main():
    import argparse
    ap = argparse.ArgumentParser()

    ap.add_argument('--nerf',action='store_const',const=True,default=False)
    ap.add_argument('--port',type=int,help='port to run on',default=6667)
    ap.add_argument('--host',type=str,help='bind host',default='127.0.0.1')
    ap.add_argument('--debug',action='store_const',const=True, default=False,
                    dest='log',help='enable debug mode by default')
    ap.add_argument('--conf',type=str,help='config file',default=None)
    ap.add_argument('-6',action='store_const',const=True, default=False,
                    dest='ipv6',help='use ipv6')
    ap.add_argument('--trace',action='store_const',const=True,default=False,
                    dest='trace',help='function debug trace')
    ap.add_argument('--torchat',help='torchat address',default=None)
    ap.add_argument('--name',type=str,help='server name',default='nameless')
    ap.add_argument('--onion-urc',type=str,help='onion addres for s2s via URC',default=None)
    ap.add_argument('--local-urc',type=str,help='port for s2s via URC on loopback',default=None)
    ap.add_argument('--remote-urc',type=str,help='remote host for s2s via urc',default=None)
    ap.add_argument('--link-port',type=int,help='linkserv port to bind on',default=6660)
    ap.add_argument('--link-host',type=str,help='linkserv host to bind on',default='localhost')
    ap.add_argument('--no-link',action='store_const',const=True,default=False,
                    dest='no_link',help='disable incoming links')
    ap.add_argument('--link-auth',action='store_const',const=True,default=False,
                    help='require link authorization')

    # parse args
    args = ap.parse_args()
    # check for SIGHUP
    if hasattr(signal,'SIGHUP'):
        signal.signal(signal.SIGHUP,hup)
    log = args.log
    global serv
    # make server
    cfgs = { }
    if args.conf is not None:
        with open(args.conf) as r:
            cfgs = json.load(r)
    else:
        cfgs = {}
    util.toggle_trace = args.trace
    serv = server.Server(
        (args.host,args.port),args.name,
        do_log=log,
        ipv6=args.ipv6,
        configs=cfgs,
        link_auth=args.link_auth,
        poni=args.nerf and 'blah' or None
        )
    
    for t in serv.threads:
        t.start()
    link = not args.no_link
    if link:
        print ('enabling link')
    localhost = args.ipv6 and '::1' or '127.0.0.1'
    linkhost = args.link_host != 'localhost' and args.link_host or localhost
    link = s2s.linkserv(serv,(linkhost,args.link_port),ipv6=args.ipv6,allow_link=link)
    if args.onion_urc:
        link.tor_link(args.onion_urc,6660)
    elif args.local_urc:
        link.local_link(args.local_urc)
    elif args.remote_urc:
        if args.ipv6:
            link.ipv6_link(args.remote_urc)
        else:
            link.ipv4_link(args.remote_urc)
    serv.link = link

    if args.torchat:
        tcserv = torchat.torchat(serv,args.torchat,torchat.nameless_client)
        
    # run mainloop
    try:
        asyncore.loop(use_poll=True)
    except KeyboardInterrupt:
        # kill threads
        serv.stop()


if __name__ == '__main__':
    main()
