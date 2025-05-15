from core.engine.hplayer import HPlayer2
from core.engine.playlist import Playlist

import os
import json, glob


# DIRECTORY / FILE
base_path = ['/data/usb', '/data/sync/sacvp']

# INIT HPLAYER
hplayer = HPlayer2(base_path, "/data/hplayer2-test.cfg")


# video = hplayer.addPlayer('mpv', 'video')
# video.imagetime(0)

# Sampler (play 0_* media from the same directory)
sampler = hplayer.addSampler('jp', 'audio', 1)
# lastSamplerMedia = None
# @hplayer.on('video.playing')
# def samplerPlay(ev, *args):
#     global lastSamplerMedia
#     directory = os.path.dirname(args[0])
#     mediaList = hplayer.files.listFiles(directory + '/0_*')
#     media = mediaList[0] if len(mediaList) > 0 else None
#     if lastSamplerMedia != media:
#         if not media: sampler.stop()
#         else: sampler.play(media, oneloop=True, index=0)
#         lastSamplerMedia = media
    
playlistSampler = Playlist(hplayer, 'Playlist-sampler')
playlistSampler.load(hplayer.files.listFiles('ZZ_AUDIO/*'))

# INTERFACES
hplayer.addInterface('midictrl', 'LPD8')
hplayer.addInterface('teleco')

#
# MIDI CTRL
#

# @hplayer.on('midictrl.noteon')
# def midiNoteOn(ev, *args):
#     track = None
#     if args[0]['note'] == 36:   track = playlistSampler.trackAtIndex(0)
#     elif args[0]['note'] == 37: track = playlistSampler.trackAtIndex(1)
#     elif args[0]['note'] == 38: track = playlistSampler.trackAtIndex(2)
#     elif args[0]['note'] == 39: track = 'stop'

#     if track == 'stop':
#         sampler.stop()
#     elif track:
#         sampler.play(track, oneloop=True, index=0)
        
@hplayer.on('midictrl.noteon')
@hplayer.on('midictrl.cc')
@hplayer.on('midictrl.pc')
def midiEvent(ev, *args):
    
    track = None
    
    if ev == 'midictrl.noteon':
        value = args[0]['note']    
        if value == 36:   track = playlistSampler.trackAtIndex(0)
        elif value == 37: track = playlistSampler.trackAtIndex(1)
        elif value == 38: track = playlistSampler.trackAtIndex(2)
        elif value == 39: track = 'stop'
    
    if ev == 'midictrl.cc':
        value = args[0]['control']
        if value == 12:   track = playlistSampler.trackAtIndex(3)
        elif value == 13: track = playlistSampler.trackAtIndex(4)
        elif value == 14: track = playlistSampler.trackAtIndex(5)
        elif value == 15: track = 'stop'
    
    if ev == 'midictrl.pc':
        value = args[0]['program']
        if value == 0:   track = playlistSampler.trackAtIndex(6)
        elif value == 1: track = playlistSampler.trackAtIndex(7)
        elif value == 2: track = playlistSampler.trackAtIndex(8)
        elif value == 3: track = 'stop'

    if track == 'stop':
        sampler.stop()
    elif track:
        sampler.play(track, oneloop=True, index=0)
        
#
# RUN
#

# default volume
@hplayer.on('app-run')
def init(ev, *args):
    hplayer.settings.set('volume', 100)
    hplayer.settings.set('loop', 1)


# file = hplayer.imgen.txt2img("004F006B00200073007500700065007200202764FE0F", "UCS2")
# hplayer.playlist.play(file)
            
# RUN
hplayer.run()                               						# TODO: non blocking
