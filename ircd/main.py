#!/usr/bin/env python
import server
import user
import signal, traceback, asyncore
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
    ap.add_argument('--linkserv',type=str,help='linkserv config file',default='linkserv.json')
    ap.add_argument('-6',action='store_const',const=True, default=False,dest='ipv6',help='use ipv6')
    ap.add_argument('--no-link',action='store_const',const=True,default=False,dest='no_link',help='do not use linkserv')
    # parse args
    args = ap.parse_args()
    # check for SIGHUP
    if hasattr(signal,'SIGHUP'):
        signal.signal(signal.SIGHUP,hup)
    log = args.log
    global serv
    # make server 
    cfgs = { 'adminserv' : '' }
    if not args.no_link:
        cfgs['linkserv'] = args.linkserv
    serv = server.Server((args.host,args.port),do_log=log,ipv6=args.ipv6,configs=cfgs)
    # make adminserv
    server.admin(serv,'admin.sock')
    # run mainloop
    asyncore.loop()



if __name__ == '__main__':
    main()
