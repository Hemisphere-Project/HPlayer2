$(document).ready(function() {

    var settings;
    var playlist;

    var socket = io.connect(location.protocol + '//' + document.domain + ':' + location.port);
    var last_status;
    var last_status_str;

    var playlistEnabled = true

    $('#settingsframe').attr('src', location.protocol + '//' + document.domain + ':4038')

    /*
      SOCKETIO
    */

    // CONNECT
    socket.on('connect', function() {
        console.log('SocketIO connected :)')
        socket.emit('fileslist');
        $('#link-connected').show();
        $('#link-disconnected').hide();
    });

    // DISCONNECT
    socket.on('disconnect', function() {
        console.log('SocketIO disconnected :(')
        $('#link-connected').hide();
        $('#link-disconnected').show();
    });

    // CONF
    socket.on('config', function(conf) {

        // Name
        $('#playerName').html(conf.name);

        // Playlist elements
        setElementPlaylist(conf.playlist)

        // Loop elements
        setElementLoop(conf.loop)

        // Mute elements
        setElementMute(conf.mute)

    })

    // FILES LIST
    socket.on('files', function(msg) {

        $('#trees').empty()

        msg.forEach(function(element) {
            var col = $('<div class="col-xl-12 col-lg-12 col-md-12 col-sm-12 " />').appendTo($('#trees'))
            var head = $('<div class="card-header text-white bg-dark">').html('<span>' + element['path'] + '</span>').appendTo(col)
            var upload = $('<span class="badge badge-info float-right">upload</span>').appendTo(head).on('click', function() {
                $('#uploadModal').modal()
            })

            var tree = $('<div class="tree mb-3" />').appendTo(col)
                // $('<br />').appendTo($('#trees'))

            tree.treeview({
                data: element['nodes'],
                selectable: true,
                multiSelect: true,
                color: "#000000",
                showTags: true
            });
            tree.on('nodeSelected', function(event, data) {
                if (!playlistEnabled) tree.treeview('unselectAll')
            });

            tree.on('nodeClicked', function(event, data) {
                if (!playlistEnabled) trigger('play', data.path);
            });

            // tree.treeview('collapseAll')
        });
    });

    // STATUS
    socket.on('status', function(msg) {

        //console.log(msg)

        // TIME
        $('#time_ellapsed').text(msg['time'])
        delete msg['time']

        // STATUS
        var str_msg = JSON.stringify(msg)
        $('#log1').text(str_msg)
        if (last_status_str != str_msg) {
            last_status = msg
            last_status_str = str_msg

            playBtn.setState(msg['isPlaying'])
            pauseBtn.setState(msg['isPaused'])
            stopBtn.setState(!msg['isPaused'] && !msg['isPlaying'])

            $('#media_name').text(msg['media'])
            playlistMedia()

            $("button").blur();
        }

    });

    // SETTINGS
    socket.on('settings.updated', function(msg) {

        // console.log(msg)
        var str_msg = JSON.stringify(msg)
        $('#log2').text(str_msg)

        loopAllBtn.setState((msg['loop'] == 2))
        loopOneBtn.setState((msg['loop'] == 1))
        autoBtn.setState(msg['autoplay'])
        muteBtn.setState(msg['mute'])
        monoBtn.setState((msg['audiomode'] == 'mono'))
        jackBtn.setState((msg['audioout'] == 'jack'))
        hdmiBtn.setState((msg['audioout'] == 'hdmi'))
        usbBtn.setState((msg['audioout'] == 'usb'))

        $('#volume_range').val(msg['volume'])
        $('#volumeMain').html(msg['volume'])

        $('#left_range').val(msg['pan'][0])
        $('#volumeLeft').html(msg['pan'][0])

        $('#right_range').val(msg['pan'][1])
        $('#volumeRight').html(msg['pan'][1])

        $("button").blur();

        settings = msg
    });

    // PLAYLIST
    socket.on('playlist.updated', function(msg) {
        var liste = [];
        if (msg)
            msg.forEach(function(el) {

                var txt = el + '<div class="media-edit float-right">'
                txt += ' <span class="badge badge-danger" onClick="playlistRemove(\'' + liste.length + '\'); event.stopPropagation();"> <i class="fas fa-ban"></i> </span>'
                txt += '</div>'

                liste.push({
                    text: txt,
                    path: el,
                    selectable: false
                })
            });

        var tree = $('#playlist')
        tree.treeview({
            data: liste,
            selectable: false,
            multiSelect: false,
            color: "#eee",
            backColor: "#333",
            onhoverColor: "#555",
            showTags: true
        })

        tree.on('nodeClicked', function(event, data) {
            trigger('playindex', data.nodeId);
        });

        playlistMedia()
    });

    // LOGS
    socket.on('logs', function(msg) {
        console.log(msg)

        var d = $('#log3')
        var cmd = msg.shift()

        $('<div>').addClass("col-lg-6 col-12").appendTo('#log3')
            .append($('<div>').addClass("row")
                .append($('<div>').addClass("col-4").html('<strong>' + cmd + '</strong>'))
                .append($('<div>').addClass("col-6").html(msg.join('&nbsp;&nbsp;')))
            ).fadeTo(3000, 0.4, function() { $(this).fadeTo(5000, 0.1) })

        $('#log3').scrollTop(d.prop("scrollHeight"));
    });

    /*
        ELEMENTS MODE
    */

    setElementPlaylist = function(mode) {
        playlistEnabled = mode !== false
        if (playlistEnabled) {
            $('.playlist-element').show()
        } else {
            $('.playlist-element').hide()
        }
        playlistBtn.setState(playlistEnabled)
    }

    setElementLoop = function(mode) {
        if (mode === false) {
            $('.loop-element').hide()
        }
    }

    setElementMute = function(mode) {
        if (mode === false) {
            $('.mute-element').hide()
        }
    }

    /*
      BUTTONS
    */

    function trigger(ev, data) {
        msg = {}
        msg['event'] = ev
        msg['data'] = data
        socket.emit('event', msg)
    }

    class Button {
        constructor(selector, style, stateAction) {
            this.btn = $(selector)
            this.style = style
            if (stateAction !== undefined) this.setState = stateAction
            this.setState(false)
        }

        outline(toggle) {
            if (toggle) {
                this.btn.removeClass('btn-' + this.style)
                this.btn.addClass('btn-outlined-' + this.style)
            } else {
                this.btn.removeClass('btn-outlined-' + this.style)
                this.btn.addClass('btn-' + this.style)
            }
        }

        setState(state) {
            this.outline(!state) // default
        }
    }

    // PLAY
    var playBtn = new Button('#play_btn', 'success')
    playBtn.btn.click(event => {
        if (!last_status['isPaused']) trigger('play');
        else trigger('resume');
    });

    // PAUSE
    var pauseBtn = new Button('#pause_btn', 'warning')
    pauseBtn.btn.click(event => {
        if (!last_status['isPaused']) trigger('pause');
        else trigger('resume');
    });

    // PREV
    var prevBtn = new Button('#prev_btn', 'secondary')
    prevBtn.btn.click(event => {
        trigger('prev');
    });

    // NEXT
    var nextBtn = new Button('#next_btn', 'secondary')
    nextBtn.btn.click(event => {
        trigger('next');
    });

    // STOP
    var stopBtn = new Button('#stop_btn', 'danger')
    stopBtn.btn.click(event => {
        trigger('stop');
    });

    // LOOPALL
    var loopAllBtn = new Button('#loopAll_btn', 'info')
    loopAllBtn.btn.click(event => {
        if (settings['loop'] != 2) trigger('loop', 2);
        else trigger('unloop');
    });

    // LOOPONE
    var loopOneBtn = new Button('#loopOne_btn', 'info')
    loopOneBtn.btn.click(event => {
        if (settings['loop'] != 1) trigger('loop', 1);
        else trigger('unloop');
    });

    // AUTOPLAY
    var autoBtn = new Button('#auto_btn', 'secondary')
    autoBtn.btn.click(event => {
        if (!settings['autoplay']) trigger('autoplay', 1);
        else trigger('autoplay', 0);
    });

    // MUTE
    var muteBtn = new Button('#mute_btn', 'warning')
    muteBtn.btn.click(event => {
        if (!settings['mute']) trigger('mute');
        else trigger('unmute');
    });

    // MONO
    var monoBtn = new Button('#mono_btn', 'secondary')
    monoBtn.btn.click(event => {
        if (settings['audiomode'] == 'mono') trigger('audiomode', 'stereo');
        else trigger('audiomode', 'mono');
    });

    // JACK
    var jackBtn = new Button('#jack_btn', 'info')
    jackBtn.btn.click(event => {
        if (confirm("Switch audio to Jack ?\nHplayer2 will restart ... (~15s) "))
            trigger('audioout', 'jack');
    });

    // HDMI
    var hdmiBtn = new Button('#hdmi_btn', 'info')
    hdmiBtn.btn.click(event => {
        if (confirm("Switch audio to HDMI ?\nHplayer2 will restart ... (~15s) "))
            trigger('audioout', 'hdmi');
    });

    // USB
    var usbBtn = new Button('#usb_btn', 'info')
    usbBtn.btn.click(event => {
        if (confirm("Switch audio to USB ?\nHplayer2 will restart ... (~15s) "))
            trigger('audioout', 'usb');
    });

    // REBOOT
    var rebootBtn = new Button('#reboot_btn', 'danger')
    rebootBtn.btn.click(event => {
        var r = confirm("Reboot the device ?");
        if (r == true) socket.emit('reboot');
    });

    // RESTART
    var restartBtn = new Button('#restart_btn', 'danger')
    restartBtn.btn.click(event => {
        var r = confirm("Restart HPlayer2 ?");
        if (r == true) socket.emit('restart');
    });

    // VOLUME
    $('#volume_range').on('input', event => {
        trigger('volume', $('#volume_range').val());
        if ($('#volume_range').val() > 100) $('#volume_range').addClass('overload')
        else $('#volume_range').removeClass('overload')
    });

    // VOLUME LEFT
    $('#left_range').on('input', event => {
        trigger('pan', [$('#left_range').val(), $('#right_range').val()]);
    });

    // VOLUME RIGHT
    $('#right_range').on('input', event => {
        trigger('pan', [$('#left_range').val(), $('#right_range').val()]);
    });

    // VOLUME EXTENDED
    $('.vol-main').on('click', event => {
        $('.vol-more').toggle()
    });
    $('.vol-more').hide()

    // PLAYLIST
    var playlistBtn = new Button('#playlist_btn', 'info')
    playlistBtn.btn.click(event => {
        setElementPlaylist(!playlistEnabled)
    });

    // LOGS
    var logsBtn = new Button('#logs_btn', 'secondary')
    logsBtn.btn.click(event => {
        $('.log-data').toggle()
    });

    // SETTINGS
    var settings = new Button('#settings_btn', 'warning')
    settings.btn.click(event => {
        $('.settings-view').toggle()
    });


    /*
      MEDIA CTRL
    */

    mediaRemove = function(path) {
        var r = confirm("Delete\n" + path + "\n?!");
        if (r == true) {
            socket.emit('filesdelete', [path])
            $(".tree").each(function(index) { $(this).treeview('unselectAll') });
        }
    }

    mediaRemoveSelected = function() {
        var selected = []
        $(".tree").each(function(index) {
            $(this).treeview('getSelected').forEach(function(el) {
                selected.push(el.path)
            })
        });
        var r = confirm("Delete \n" + selected.join('\n') + "\n?!");
        if (r == true) {
            socket.emit('filesdelete', selected)
            $(".tree").each(function(index) { $(this).treeview('unselectAll') });
        }
    }

    mediaEdit = function(path) {
        filename = path.split('/').pop().split('.').slice(0, -1).join('.');
        ext = path.split('.').pop()
        basepath = path.split(filename)[0]

        rename = window.prompt('Edit file name:', filename);

        if (rename && rename.charAt(0) != '.') {
            newpath = basepath + rename + '.' + ext
            console.info(newpath);
            socket.emit('filerename', path, newpath)
        }
    }

    mediaDownload = function(path) {
        var a = document.createElement("a");
        document.body.appendChild(a);
        a.style = "display: none";
        a.href = "/filedownload?path=" + path;
        a.download = path.split('/').pop();
        a.click()
        a.remove()
    }

    /*
      PLAYLIST
    */

    $('#clear_btn').click(event => {
        trigger('clear')
    });

    playlistAdd = function(path) {
        trigger('add', path)
        return false;
    };

    playlistAddSelected = function() {
        var selected = []
        $(".tree").each(function(index) {
            $(this).treeview('getSelected').forEach(function(el) {
                selected.push(el.path)
            })
        });
        trigger('add', selected)
        $(".tree").each(function(index) { $(this).treeview('unselectAll') });
    };

    playlistRemove = function(path) {
        trigger('remove', path)
        return false;
    };

    playlistMedia = function() {
        if ($('#playlist').length == 0) return
        
        $('#playlist').treeview('getNodes').forEach(function(node) {
            if (last_status && (node.nodeId == last_status['index'])) node.backColor = "#343"
            else node.backColor = "#333"
        });
        $('#playlist').treeview('render')
    }


    /*
      SELECTION
    */

    $('#delsel_btn').click(mediaRemoveSelected);

    $('#playsel_btn').click(playlistAddSelected);

    $('#selall_btn').click(event => {
        $(".tree").each(function(index) {
            $(this).treeview('selectAll')
        });
    });

    $('#selnone_btn').click(event => {
        $(".tree").each(function(index) {
            $(this).treeview('unselectAll')
        });
    });

});