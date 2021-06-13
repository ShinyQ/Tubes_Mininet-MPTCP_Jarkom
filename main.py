from mininet.topo import Topo
from mininet.net import Mininet
from mininet.node import Node
from mininet.cli import CLI
from mininet.link import TCLink
from mininet.log import setLogLevel
from datetime import datetime

import os
import time

class LinuxRouter(Node):
    "A Node with IP forwarding enabled."

    def config(self, **params):
        super(LinuxRouter, self).config(**params)
        self.cmd('sysctl net.ipv4.ip_forward=1')

    def terminate(self):
        self.cmd('sysctl net.ipv4.ip_forward=0')
        super(LinuxRouter, self).terminate()


class NetworkTopo(Topo):

    def build(self, **_opts):

        # Menambahkan router r1-r4
        r1 = self.addNode('r1', cls=LinuxRouter, ip='192.168.2.1/24')
        r2 = self.addNode('r2', cls=LinuxRouter, ip='192.168.3.1/24')
        r3 = self.addNode('r3', cls=LinuxRouter, ip='192.168.2.2/24')
        r4 = self.addNode('r4', cls=LinuxRouter, ip='192.168.3.2/24')

        # Menambahkan host hA & hB
        hA = self.addHost('hA', ip='192.168.0.2/24', defaultRoute='via 192.168.0.1')
        hB = self.addHost('hB', ip='192.168.4.2/24', defaultRoute='via 192.168.4.1')
        
        # Menambahkan links pada nodes
        # Router <--> Router
        # Ukuran Queue : 20, 40, 60 dan 100

        linkopts0 = dict(bw=0.5, delay='1ms', loss=0, max_queue_size=20, use_tbf=True)
        linkopts1 = dict(bw=1, delay='1ms', loss=0, max_queue_size=20, use_tbf=True)

        self.addLink(r1, r3, cls=TCLink, **linkopts0, intfName1='r1-eth1', intfName2='r3-eth1',
                     params1={'ip': '192.168.2.1/24'}, 
                     params2={'ip': '192.168.2.2/24'})

        self.addLink(r1, r4, cls=TCLink, **linkopts1, intfName1='r1-eth2', intfName2='r4-eth1',
                     params1={'ip': '192.168.6.1/24'}, 
                     params2={'ip': '192.168.6.2/24'})

        self.addLink(r2, r4, cls=TCLink, **linkopts0, intfName1='r2-eth1', intfName2='r4-eth2',
                     params1={'ip': '192.168.3.1/24'}, 
                     params2={'ip': '192.168.3.2/24'})

        self.addLink(r2, r3, cls=TCLink, **linkopts1, intfName1='r2-eth2', intfName2='r3-eth2',
                     params1={'ip': '192.168.7.1/24'}, 
                     params2={'ip': '192.168.7.2/24'})
                     
        # Router <--> Host

        self.addLink(hA, r1, cls=TCLink, **linkopts1,  intfName2='r1-eth3',
                     params1={'ip': '192.168.0.2/24'}, 
                     params2={'ip': '192.168.0.1/24'})

        self.addLink(hA, r2, cls=TCLink, **linkopts1, intfName2='r2-eth3',
                     params1={'ip': '192.168.1.2/24'}, 
                     params2={'ip': '192.168.1.1/24'})

        self.addLink(hB, r3, cls=TCLink, **linkopts1, intfName2='r3-eth3',
                     params1={'ip': '192.168.4.2/24'}, 
                     params2={'ip': '192.168.4.1/24'})

        self.addLink(hB, r4, cls=TCLink, **linkopts1, intfName2='r4-eth3',
                     params1={'ip': '192.168.5.2/24'}, 
                     params2={'ip': '192.168.5.1/24'})


def run():
    net = Mininet(topo=NetworkTopo())
    net.start()

    time_start = datetime.now()

    print("*** Setup quagga")
    for router in net.hosts:
        if router.name[0] == 'r':

            # config zebra and ripd
            router.cmd("zebra -f config/zebra/{0}zebra.conf -d -i /tmp/{0}zebra.pid > logs/{0}-zebra-stdout 2>&1".format(router.name))
            router.waitOutput()
            
            router.cmd("ripd -f config/rip/{0}ripd.conf -d -i /tmp/{0}ripd.pid > logs/{0}-ripd-stdout 2>&1".format(router.name), shell=True)
            router.waitOutput()
            
            print(f"Starting zebra and rip on {router.name}")

    # MPTCP Static Routing
    net['hA'].cmd("ip rule add from 192.168.0.2 table 1")
    net['hA'].cmd("ip rule add from 192.168.1.2 table 2")
    net['hA'].cmd("ip route add 192.168.0.0/24 dev hA-eth0 scope link table 1")
    net['hA'].cmd("ip route add default via 192.168.0.1 dev hA-eth0 table 1")
    net['hA'].cmd("ip route add 192.168.1.0/24 dev hA-eth1 scope link table 2")
    net['hA'].cmd("ip route add default via 192.168.1.1 dev hA-eth1 table 2")
    net['hA'].cmd("ip route add default scope global nexthop via 192.168.0.1 dev hA-eth0")
    
    net['hB'].cmd("ip rule add from 192.168.4.2 table 1")
    net['hB'].cmd("ip rule add from 192.168.5.2 table 2")
    net['hB'].cmd("ip route add 192.168.4.0/24 dev hB-eth0 scope link table 1")
    net['hB'].cmd("ip route add default via 192.168.4.1 dev hB-eth0 table 1")
    net['hB'].cmd("ip route add 192.168.5.0/24 dev hB-eth1 scope link table 2")
    net['hB'].cmd("ip route add default via 192.168.5.1 dev hB-eth1 table 2")
    net['hB'].cmd("ip route add default scope global nexthop via 192.168.4.1 dev hB-eth0")

    #time.sleep(5)
    print("\n*** Connection test")
    
    loss = 100
    while(loss > 0):
        loss = net.pingAll()

    time_end = datetime.now() - time_start
    print(f'Percentage Loss : {loss}')
    print(f'Convergence Time: {time_end.total_seconds()}s')
    

    print("\n*** Bandwidth test")
    time.sleep(5)

    net['hB'].cmd('iperf -s -i 1 &')
    time.sleep(1)

    net['hA'].cmdPrint('iperf -c 192.168.5.2 -i 1')
    CLI(net)

    net.stop()
    os.system("killall -9 zebra ripd")
    os.system("rm -f /tmp/*.log /tmp/*.pid logs/*")


os.system("rm -f /tmp/*.log /tmp/*.pid logs/*")
os.system("mn -cc")
os.system("clear")

setLogLevel('info')
run()