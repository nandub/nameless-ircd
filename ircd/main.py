#!/usr/bin/env python
import server, user, adminserv
import signal, traceback, asyncore, json, sys
from threading import Thread
serv = None
def hup(sig,frame):
    '''
    called on SIGHUP
    '''
    print 'reload'
    try:
        global serv
        serv.reload()
    except:
        print 'Error reloading'
        print traceback.format_exc()
    else:
        print 'okay'


def main():
    import argparse
    ap = argparse.ArgumentParser()
    ap.add_argument('--port',type=int,help='port to run on',default=6666)
    ap.add_argument('--host',type=str,help='bind host',default='127.0.0.1')
    ap.add_argument('--log',action='store_const',const=True, default=False,dest='log',help='enable logging by default')
    ap.add_argument('--conf',type=str,help='config file',default=None)
    ap.add_argument('-6',action='store_const',const=True, default=False,dest='ipv6',help='use ipv6')
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
        cfgs = {'adminserv' : ''}

    serv = server.Server((args.host,args.port),do_log=log,ipv6=args.ipv6,configs=cfgs)
    # make adminserv
    adminserv.handler(serv,'admin.sock')
    # start mainloop
    for t in serv.threads:
        t.start()
    # run mainloop
    try:
        asyncore.loop()
    except KeyboardInterrupt:
        # kill threads
        serv.on = False
        for t in serv.threads:
            t.join()



if __name__ == '__main__':
    main()
