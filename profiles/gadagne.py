from core.engine import hplayer

# PLAYER
player = hplayer.addplayer('mpv', 'gadagne')

# Interfaces
player.addInterface('osc', 4000, 4001)
player.addInterface('http', 8080)
# player.addInterface('gpio', [16,19,20,21,26])

# GADAGNE logic
defaultFile = 'media0.mp4'
push1File = 'media1.mp4'
push2File = 'media2.mp4'
push3File = 'media3.mp4'

# Loop default file
player.on('end', lambda: player.play(defaultFile))

# HTTP + GPIO events
player.on(['push1', 'gpio20'], lambda: player.play(push1File))
player.on(['push2', 'gpio21'], lambda: player.play(push2File))
player.on(['push3', 'gpio26'], lambda: player.play(push3File))

fails = 5

# RUN
hplayer.setBasePath("/home/pi/Videos/")
hplayer.run()
