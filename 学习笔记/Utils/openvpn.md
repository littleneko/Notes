# 下载链接
- github repositery: [https://github.com/OpenVPN/openvpn](https://github.com/OpenVPN/openvpn)
- sample server config: [https://github.com/OpenVPN/openvpn/blob/master/sample/sample-config-files/server.conf](https://github.com/OpenVPN/openvpn/blob/master/sample/sample-config-files/server.conf)
- sample client config: [https://github.com/OpenVPN/openvpn/blob/master/sample/sample-config-files/client.conf](https://github.com/OpenVPN/openvpn/blob/master/sample/sample-config-files/client.conf)
- easy-rsa: [https://github.com/OpenVPN/easy-rsa](https://github.com/OpenVPN/easy-rsa)

# easy-rsa
### 编辑vars文件
`cp vars.example vars` and edit `vars`

<img src="https://littleneko.oss-cn-beijing.aliyuncs.com/img/1591548009520-98f235de-6f0f-40ff-b770-d7aae73c9fd9.png" alt="image.png" style="zoom:50%;" />

### 创建空的PKI
```shell
ubuntu@VM-0-8-ubuntu:~/EasyRSA-3.0.7$ ./easyrsa init-pki

Note: using Easy-RSA configuration from: /home/ubuntu/EasyRSA-3.0.7/vars

init-pki complete; you may now create a CA or requests.
Your newly created PKI dir is: /home/ubuntu/EasyRSA-3.0.7/pki
```


### 创建新的CA，不需要password
```shell
ubuntu@VM-0-8-ubuntu:~/EasyRSA-3.0.7$ ./easyrsa build-ca nopass

Note: using Easy-RSA configuration from: /home/ubuntu/EasyRSA-3.0.7/vars
Using SSL: openssl OpenSSL 1.1.1  11 Sep 2018
Generating RSA private key, 2048 bit long modulus (2 primes)
..........+++++
...............................+++++
e is 65537 (0x010001)
You are about to be asked to enter information that will be incorporated
into your certificate request.
What you are about to enter is what is called a Distinguished Name or a DN.
There are quite a few fields but you can leave some blank
For some fields there will be a default value,
If you enter '.', the field will be left blank.
-----
Common Name (eg: your user, host, or server name) [Easy-RSA CA]:littleneko.org

CA creation complete and you may now import and sign cert requests.
Your new CA certificate file for publishing is at:
/home/ubuntu/EasyRSA-3.0.7/pki/ca.crt
```


### 创建服务端证书
```shell
ubuntu@VM-0-8-ubuntu:~/EasyRSA-3.0.7$ ./easyrsa gen-req server nopass

Note: using Easy-RSA configuration from: /home/ubuntu/EasyRSA-3.0.7/vars
Using SSL: openssl OpenSSL 1.1.1  11 Sep 2018
Generating a RSA private key
.+++++
..............+++++
writing new private key to '/home/ubuntu/EasyRSA-3.0.7/pki/easy-rsa-27662.6SJ7Hk/tmp.kKkhnX'
-----
You are about to be asked to enter information that will be incorporated
into your certificate request.
What you are about to enter is what is called a Distinguished Name or a DN.
There are quite a few fields but you can leave some blank
For some fields there will be a default value,
If you enter '.', the field will be left blank.
-----
Common Name (eg: your user, host, or server name) [server]:vpnserver1.littleneko.org

Keypair and certificate request completed. Your files are:
req: /home/ubuntu/EasyRSA-3.0.7/pki/reqs/server.req
key: /home/ubuntu/EasyRSA-3.0.7/pki/private/server.key
```
### 签名服务端证书
```shell
ubuntu@VM-0-8-ubuntu:~/EasyRSA-3.0.7$ ./easyrsa sign server server

Note: using Easy-RSA configuration from: /home/ubuntu/EasyRSA-3.0.7/vars
Using SSL: openssl OpenSSL 1.1.1  11 Sep 2018


You are about to sign the following certificate.
Please check over the details shown below for accuracy. Note that this request
has not been cryptographically verified. Please be sure it came from a trusted
source or that you have verified the request checksum with the sender.

Request subject, to be signed as a server certificate for 825 days:

subject=
    commonName                = vpnserver1.littleneko.org


Type the word 'yes' to continue, or any other input to abort.
  Confirm request details: yes
Using configuration from /home/ubuntu/EasyRSA-3.0.7/pki/easy-rsa-27828.v3KsaB/tmp.IqLKp3
Check that the request matches the signature
Signature ok
The Subject's Distinguished Name is as follows
commonName            :ASN.1 12:'vpnserver1.littleneko.org'
Certificate is to be certified until Sep 10 16:47:35 2022 GMT (825 days)

Write out database with 1 new entries
Data Base Updated

Certificate created at: /home/ubuntu/EasyRSA-3.0.7/pki/issued/server.crt
```
### 创建Diffie-Hellman
```shell
ubuntu@VM-0-8-ubuntu:~/EasyRSA-3.0.7$ ./easyrsa gen-dh

Note: using Easy-RSA configuration from: /home/ubuntu/EasyRSA-3.0.7/vars
Using SSL: openssl OpenSSL 1.1.1  11 Sep 2018
Generating DH parameters, 2048 bit long safe prime, generator 2
This is going to take a long time
........................................++*++*++*++*

DH parameters of size 2048 created at /home/ubuntu/EasyRSA-3.0.7/pki/dh.pem
```
### 创建客户端证书
```shell
ubuntu@VM-0-8-ubuntu:~/EasyRSA-3.0.7$ ./easyrsa gen-req dalin nopass

Note: using Easy-RSA configuration from: /home/ubuntu/EasyRSA-3.0.7/vars
Using SSL: openssl OpenSSL 1.1.1  11 Sep 2018
Generating a RSA private key
...............................................+++++
...........................................................................................+++++
writing new private key to '/home/ubuntu/EasyRSA-3.0.7/pki/easy-rsa-28409.JKQfYu/tmp.Ozdfm9'
-----
You are about to be asked to enter information that will be incorporated
into your certificate request.
What you are about to enter is what is called a Distinguished Name or a DN.
There are quite a few fields but you can leave some blank
For some fields there will be a default value,
If you enter '.', the field will be left blank.
-----
Common Name (eg: your user, host, or server name) [dalin]:dalin

Keypair and certificate request completed. Your files are:
req: /home/ubuntu/EasyRSA-3.0.7/pki/reqs/dalin.req
key: /home/ubuntu/EasyRSA-3.0.7/pki/private/dalin.key
```
### 签名客户端证书
```shell
ubuntu@VM-0-8-ubuntu:~/EasyRSA-3.0.7$ /easyrsa sign client dalin
-bash: /easyrsa: No such file or directory
ubuntu@VM-0-8-ubuntu:~/EasyRSA-3.0.7$ ./easyrsa sign client dalin

Note: using Easy-RSA configuration from: /home/ubuntu/EasyRSA-3.0.7/vars
Using SSL: openssl OpenSSL 1.1.1  11 Sep 2018


You are about to sign the following certificate.
Please check over the details shown below for accuracy. Note that this request
has not been cryptographically verified. Please be sure it came from a trusted
source or that you have verified the request checksum with the sender.

Request subject, to be signed as a client certificate for 825 days:

subject=
    commonName                = dalin


Type the word 'yes' to continue, or any other input to abort.
  Confirm request details: yes
Using configuration from /home/ubuntu/EasyRSA-3.0.7/pki/easy-rsa-28856.WpwN2R/tmp.qF0UaK
Check that the request matches the signature
Signature ok
The Subject's Distinguished Name is as follows
commonName            :ASN.1 12:'dalin'
Certificate is to be certified until Sep 10 16:54:03 2022 GMT (825 days)

Write out database with 1 new entries
Data Base Updated

Certificate created at: /home/ubuntu/EasyRSA-3.0.7/pki/issued/dalin.crt
```
### 整理相关文件
server 需要
```shell
ubuntu@VM-0-8-ubuntu:~/EasyRSA-3.0.7$ sudo cp pki/ca.crt /etc/openvpn/certs/
ubuntu@VM-0-8-ubuntu:~/EasyRSA-3.0.7$ sudo cp pki/dh.pem /etc/openvpn/certs/
ubuntu@VM-0-8-ubuntu:~/EasyRSA-3.0.7$ sudo cp pki/issued/server.crt /etc/openvpn/certs/
ubuntu@VM-0-8-ubuntu:~/EasyRSA-3.0.7$ sudo cp pki/private/server.key /etc/openvpn/certs/
```
client 需要
```shell
ubuntu@VM-0-8-ubuntu:~/EasyRSA-3.0.7$ cp pki/ca.crt ../client_certs/
ubuntu@VM-0-8-ubuntu:~/EasyRSA-3.0.7$ cp pki/issued/dalin.crt ../client_certs/
ubuntu@VM-0-8-ubuntu:~/EasyRSA-3.0.7$ cp pki/private/dalin.key ../client_certs/
```
# config
## server
```
port 1194
proto tcp
dev tap
ca /etc/openvpn/certs/ca.crt
cert /etc/openvpn/certs/server.crt
key /etc/openvpn/certs/server.key  # This file should be kept secret
dh /etc/openvpn/certs/dh.pem
server 10.8.0.0 255.255.255.0
ifconfig-pool-persist /var/log/openvpn/ipp.txt
push "redirect-gateway def1 bypass-dhcp"
push "dhcp-option DNS 10.8.0.1"
client-to-client
keepalive 10 120
cipher AES-256-CBC
comp-lzo
persist-key
persist-tun
status /var/log/openvpn/openvpn-status.log
log         /var/log/openvpn/openvpn.log
verb 3
```
## client
```
client
dev tap
proto tcp
remote 148.70.24.48 1194
resolv-retry infinite
nobind
persist-key
persist-tun
ca ca.crt
cert along.crt
key along.key
remote-cert-tls server
cipher AES-256-CBC
comp-lzo
verb 3
```
# ROUTING ALL CLIENT TRAFFIC (INCLUDING WEB-TRAFFIC) THROUGH THE VPN

1. add `push "redirect-gateway def1"` to server.conf
1. open ip_forward on server
   1. `echo "net.ipv4.ip_forward=1" >> /etc/eysctl.conf` 
   1. `sudo sysctl -p` 
3. `iptables -t nat -A POSTROUTING -s 10.8.0.0/24 -o eth0 -j MASQUERADE` 
3. add  `push "dhcp-option DNS 10.8.0.1"` to server.conf



## About redirect-gateway
(Experimental) Automatically execute routing commands to cause all outgoing IP traffic to be redirected over the VPN.This option performs three steps:


(1) Create a static route for the –remote address which forwards to the pre-existing default gateway. This is done so that (3) will not create a routing loop.
(2) Delete the default gateway route.
(3) Set the new default gateway to be the VPN endpoint address (derived either from –route-gateway or the second parameter to –ifconfig when –dev tun is specified).



Before connected to openvpn server

<img src="https://littleneko.oss-cn-beijing.aliyuncs.com/img/1591550875371-747338d0-ff94-4e3c-9169-3d4b8662063b.png" alt="image.png" style="zoom:50%;" />

After connected to openvpn

<img src="https://littleneko.oss-cn-beijing.aliyuncs.com/img/1591551407693-70baa153-7ac4-4432-8682-f07310c50b57.png" alt="image.png" style="zoom:50%;" />


# Links

1. [https://openvpn.net/community-resources/how-to/#openvpn-quickstart](https://openvpn.net/community-resources/how-to/#openvpn-quickstart)
1. [https://community.openvpn.net/openvpn](https://community.openvpn.net/openvpn)
1. [https://openvpn.net/community-resources/reference-manual-for-openvpn-2-0/](https://openvpn.net/community-resources/reference-manual-for-openvpn-2-0/)
