rw && cd /opt/HPlayer2 && ./datesync && git reset --hard origin/master && git fetch && git checkout anna-player && reboot
scp 0_loop.mp4 root@10.0.0.231:/data/media/ && scp 1_jellyfish.mp4 root@10.0.0.231:/data/media/

 1 = 227 - OK xx
 2 = 240 - OK 
 3 = 231 - OK 
 4 = 156 - OK 
 5 = 173 - OK x
 6 = 229 - OK xx
 7 = 214 - OK xx
 8 = 239 - OK xx
 9 = 198 - OK x 
10 = 190 - OK xx


when other play media reset masterloopindex

journalctl -fe -u hplayer2@anna | grep -Fv -e 'peer.link' -e 'accuracy' -e 'correction' -e 'clock shift'

rw && cd /opt/HPlayer2 && git checkout master && git pull && reboot
cd /opt/HPlayer2 && rw && git branch && git pull && ro && exit
