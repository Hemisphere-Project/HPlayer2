from core.interfaces.kyre import KyreNode
from time import sleep

def proc(data):
    print('PROC', data)

node = KyreNode(proc)

while True:
    try:
        sleep(1)
    except KeyboardInterrupt:
        break

node.stop()
sleep(1)
print("Bye!")
