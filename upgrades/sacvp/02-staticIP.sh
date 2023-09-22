
#!/bin/bash

# exit when any command fails
set -e

# keep track of the last executed command
trap 'last_command=$current_command; current_command=$BASH_COMMAND' DEBUG
# echo an error message before exiting
trap 'echo "\"${last_command}\" command filed with exit code $?."' EXIT

rw 
chmod -R 777 /tmp
date -s "$(curl -s --head http://google.com | grep ^Date: | sed 's/Date: //g')"

##
## Clean name
##
nameA=$(cat /etc/hostname)
nameB=$(echo "$nameA" | tr '[:upper:]' '[:lower:]')
nameB="$(tr '[:lower:]' '[:upper:]' <<< ${nameB:0:1})${nameB:1}"
sed -i "s/@$nameA/@$nameB/" /boot/starter.txt

##
## Static IP
##
ord() {
  LC_CTYPE=C printf '%d' "'$1"
}
firstletter=${nameB:0:1}
idW=$(ord $firstletter)
idI=$(expr $idW - 64)

if test -f "/boot/wifi/eth0-dhcp.nmconnection"; then
    mv /boot/wifi/eth0-dhcp.nmconnection /boot/wifi/_disabled/
fi
echo "[connection]
id=eth0-static
type=ethernet
interface-name=eth0
permissions=

[ethernet]
mac-address-blacklist=

[ipv4]
address1=10.0.10.$idI/16,10.0.0.1
dns-search=
method=manual

[ipv6]
addr-gen-mode=stable-privacy
dns-search=
method=disabled
" > /boot/wifi/eth0-static.nmconnection

echo "[connection]
id=wlan0-kxkm24
type=wifi
autoconnect=true
autoconnect-priority=4
autoconnect-retries=0
interface-name=wlan0
permissions=

[wifi]
hidden=true
mac-address-blacklist=
mode=infrastructure
ssid=kxkm24

[ipv4]
address1=10.0.9.$idI/16,10.0.0.1
dns-search=
method=manual

[ipv6]
addr-gen-mode=stable-privacy
dns-search=
method=disabled
" > /boot/wifi/wlan0-kxkm24.nmconnection

echo "[connection]
id=wlan0-kxkm5
type=wifi
autoconnect=true
autoconnect-priority=5
autoconnect-retries=0
interface-name=wlan0
permissions=

[wifi]
hidden=true
mac-address-blacklist=
mode=infrastructure
ssid=kxkm5

[ipv4]
address1=10.0.9.$idI/16,10.0.0.1
dns-search=
method=manual

[ipv6]
addr-gen-mode=stable-privacy
dns-search=
method=disabled
" > /boot/wifi/wlan0-kxkm5.nmconnection


echo '02-staticIP' >> /boot/VERSION
echo "SUCCESS !" 
reboot
