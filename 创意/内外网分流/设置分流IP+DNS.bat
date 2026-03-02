@echo off
:: 设置内网网卡 IP、网关和 DNS
netsh interface ip set address name="以太网" static 10.30.44.154 255.255.255.0 10.30.44.254
netsh interface ip set dns name="以太网" static 10.30.5.50 primary
netsh interface ip add dns name="以太网" 10.10.1.8 index=2

:: 设置外网网卡 DNS
netsh interface ip set dns name="以太网 2" static 8.8.8.8 primary
netsh interface ip add dns name="以太网 2" 114.114.114.114 index=2

:: 设置静态路由，让 10.0.0.0/8 走内网网关
route -p add 10.0.0.0 mask 255.0.0.0 10.30.44.254 metric 1 if 12

:: 设置接口 metric（可选）
netsh interface ipv4 set interface "以太网" metric=20
netsh interface ipv4 set interface "以太网 2" metric=10

echo 配置完成！
pause
