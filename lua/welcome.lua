msg = require 'mp.msg'
msg.info("!")

--[[
osc = require 'osc'

socket = require("socket")
udp = socket.udp()
udp:setpeername("127.0.0.1", 4000)
udp:settimeout()

udp:send("Yo !")

function on_pause_change(name, value)
	local data
    
    if value == true then
        --mp.set_property("fullscreen", "no")
        mp.osd_message("Paused !")
        udp:send("/pause")
        
        local data = osc.pack('/allright', true, 2, {foo = 'bar'})
        udp:send(data )
        
	else
		--mp.set_property("fullscreen", "yes")
		mp.osd_message("UnPaused !")
		udp:send("/unpause")
    end
end
mp.observe_property("pause", "bool", on_pause_change)
--]]

