@echo off
:: 删除静态路由
route delete 10.0.0.0

:: 设置 DNS 自动获取
netsh interface ip set dns name="以太网" source=dhcp
netsh interface ip set dns name="以太网 2" source=dhcp

:: （可选）如果你设置过静态 IP，可加下面这行恢复为 DHCP：
:: netsh interface ip set address name="以太网" source=dhcp
:: netsh interface ip set address name="以太网 2" source=dhcp

:: 恢复接口 metric 为自动
netsh interface ipv4 set interface "以太网" metric=0
netsh interface ipv4 set interface "以太网 2" metric=0

echo 网络配置已恢复为默认状态！
pause
