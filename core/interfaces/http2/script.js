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

        // Brightness/contrast elements (profile-gated, hidden by default)
        setElementBrightness(conf.brightness)

        // Surface (LED transform) card (profile-gated, hidden by default)
        setElementSurface(conf.surface)

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

        // TIME + PROGRESS (hplayer2#t-043) -- the fill is written before
        // 'time' is dropped from the change-guard string below
        $('#time_ellapsed').text(msg['time'])
        seekbarTick(msg)
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
            seekbarArm(msg)

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

        $('#volume_range').val(msg['volume'])
        $('#volumeMain').html(msg['volume'])

        // brightness
        $('#brightness_range').val(msg['brightness'])
        $('#brightnessMain').html(msg['brightness'])

        // contrast
        $('#contrast_range').val(msg['contrast'])
        $('#contrastMain').html(msg['contrast'])

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

    // brightness + contrast sliders: only the videonet backend drives them,
    // every other player no-ops the two events — so they stay hidden unless
    // the profile opts in: addInterface('http2', 80, {'brightness': True})
    // (hplayer2#t-042). Hidden by style.css until then: no flash on load.
    setElementBrightness = function(mode) {
        if (mode === true) {
            $('.brightness-element').show()
        } else {
            $('.brightness-element').hide()
        }
    }

    // Surface (LED / output transform) card: shown when a player applies it — the
    // server resolves the gate from the players' hasSurface() (mpv with the GLSL scaler,
    // x86 only; a Pi's MMAL output has none), unless the profile forces {'surface': bool}
    setElementSurface = function(mode) {
        if (mode === true) {
            $('.surface-element').show()
        } else {
            $('.surface-element').hide()
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

    // AUDIO OUTPUT STATUS — pushed by the audiohub monitor.
    // 'hub' mode (dedicated platform, Pi-tools plumbing): every present
    // output plays, chips reflect per-forwarder health on two axes:
    // red = forwarder unit down, orange = unit up but the sink hw_ptr
    // stopped advancing while mpv plays (silent pipeline wedge). The HDMI
    // chip is also a toggle: platform softvol mute (dark = muted; error/
    // stalled outrank it — silence keeps flowing, health stays watchable).
    // 'default' mode (generic ALSA): neutral chips.
    function audioChip(sel, state, html) {
        var cls = { 'on': 'badge-success', 'active': 'badge-success',
                    'absent': 'badge-light', 'off': 'badge-light',
                    'error': 'badge-danger', 'stalled': 'badge-warning',
                    'muted': 'badge-dark',
                    'default': 'badge-secondary', 'legacy': 'badge-secondary'
                  }[state] || 'badge-secondary';
        $(sel).removeClass('badge-success badge-light badge-danger badge-warning badge-dark badge-secondary')
              .addClass(cls);
        if (html) $(sel).html(html);
    }
    var hdmiAudioState = null;   // last hub-mode hdmi chip state, null = no hub
    socket.on('audio-status', function(msg) {
        var hub = (msg['mode'] == 'hub');
        var pipe = hub ? 'audio hub ' + (msg['graph'] || '?')
                         + ' · ' + (msg['latency-ms'] || '?') + 'ms'
                       : 'default ALSA (no hub)';
        audioChip('#jack_status', msg['jack']);
        var hdmi = '<i class="fas fa-desktop"></i> HDMI';
        if (hub && msg['hdmi'] == 'muted') hdmi += ' <i class="fas fa-volume-mute"></i>';
        audioChip('#hdmi_status', msg['hdmi'], hdmi);
        var usb = '<i class="fab fa-usb"></i> USB';
        if (hub && msg['usb'] == 'active' && msg['usb-channels'])
            usb += ' ' + msg['usb-channels'] + 'ch';
        if (msg['usb'] == 'error' || msg['usb'] == 'stalled') usb += ' &#9888;';
        audioChip('#usb_status', msg['usb'], usb);
        hdmiAudioState = hub ? msg['hdmi'] : null;
        $('#hdmi_status').toggleClass('clickable', hub);
        $('#jack_status').attr('title', 'internal jack — ' + pipe);
        $('#hdmi_status').attr('title', 'HDMI audio — ' + pipe
            + (hub ? (msg['hdmi'] == 'muted' ? ' — MUTED, click to unmute'
                                             : ' — click to mute') : ''));
        $('#usb_status').attr('title', 'USB audio — ' + pipe
            + (hub && msg['usb-card'] ? ' — ' + msg['usb-card'] : ''));
    });
    $('#hdmi_status').click(function() {
        if (hdmiAudioState == null) return;      // status-only without a hub
        var mute = (hdmiAudioState != 'muted');
        if (confirm(mute ? 'Mute HDMI audio ?' : 'Unmute HDMI audio ?'))
            socket.emit('audiomute', {'mute': mute});
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
    });

    // BRIGHTNESS
    $('#brightness_range').on('input', event => {
        trigger('brightness', $('#brightness_range').val());
    })

    // CONTRAST
    $('#contrast_range').on('input', event => {
        trigger('contrast', $('#contrast_range').val());
    })

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

    /*
      PROGRESS BAR (hplayer2#t-043) -- click-to-jump only
    */
    // status() ticks at 10 Hz with time + duration in seconds. The bar is one
    // style write on a cached element, and only when the whole percent moves
    // (the same change-guard idea as last_status_str); the card is never
    // re-rendered. No drag, no scrub: a click sends one absolute seek.
    var seekFill = document.getElementById('seekbar_fill')
    var seekBar = $('#seekbar')
    var seekPct = -1        // last percent written to the DOM
    var seekDuration = 0    // seconds while seekable, else 0

    // seek acts only while playing or paused (hplayer.py 'seek' -> isPlaying()),
    // and duration is filled only by mpv -- 0 on every other backend and
    // between media loads. Live only when both hold: 0/0 never draws a full
    // bar, and a stopped player never takes a click that would do nothing.
    function seekableDuration(st) {
        return ((st['isPlaying'] || st['isPaused']) && st['duration'] > 0) ? st['duration'] : 0
    }
    // every tick: whole percent, DOM touched only when it changes
    function seekbarTick(st) {
        var d = seekableDuration(st)
        var pct = d > 0 ? Math.round(Math.max(0, Math.min(1, st['time'] / d)) * 100) : 0
        if (pct === seekPct) return
        seekPct = pct
        seekFill.style.width = pct + '%'
    }
    // on a status change only: arm / disarm the click
    function seekbarArm(st) {
        seekDuration = seekableDuration(st)
        seekBar.toggleClass('disabled', seekDuration <= 0)
    }
    seekBar.on('click', function(e) {
        if (seekDuration <= 0) return
        var r = this.getBoundingClientRect()
        if (!r.width) return
        var frac = Math.max(0, Math.min(1, (e.clientX - r.left) / r.width))
        // one absolute seek, in ms. mpv snaps to a keyframe (seekTo exact=False,
        // cheap on a Pi) and reports where it really landed on the next tick:
        // the bar draws that and never argues, so no optimistic redraw here.
        trigger('seek', Math.round(frac * seekDuration * 1000))
    })

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

    /*
      COLLAPSIBLE ADAPTER CARDS (hplayer2#t-042)
    */
    // Radar / Nowde / Schedule / DMX bodies fold on the boolean each panel
    // already renders as its badge (connected / linked / rtc / connected):
    // folded until the adapter shows up, open once it does — so a panel
    // whose interface is not even in the profile stays a one-line header.
    // The fold follows *transitions* of that boolean only: a 1-5 Hz status
    // stream never fights an operator who opened a folded card by hand, the
    // header being the toggle. Plain Bootstrap collapse, no data-api: the
    // DMX header holds a <select> that must not toggle its card.
    var panelUp = {}
    function panelFollow(body, up) {
        up = !!up
        if (panelUp[body] === up) return
        panelUp[body] = up
        $(body).collapse(up ? 'show' : 'hide')
    }
    $('.panel-toggle').on('click', function(e) {
        if ($(e.target).closest('select, input, button, a, textarea, label').length) return
        $($(this).data('body')).collapse('toggle')
    })
    $('.panel-body').on('show.bs.collapse hide.bs.collapse', function(e) {
        if (e.target !== this) return
        $(this).prev('.panel-toggle').toggleClass('open', e.type === 'show')
    })

    // --- Surface (LED / output transform) panel (kmini minis) ---
    // Each field patches ONE key of the persisted `surface` setting ({'width': 256});
    // the engine merges, cleans, persists and echoes the whole dict via settings.updated.
    (function() {
        var numKeys = ['width', 'height', 'rotate', 'source_offset_x', 'source_offset_y', 'output_x', 'output_y'];
        function fill(sf) {
            sf = sf || {};
            $('#surface_enable').prop('checked', !!sf.enable);
            $('#surface_halfheight').prop('checked', !!sf.halfheight);
            $('#surface_fit').val(sf.fit || 'cover');
            $('#surface_align').val(sf.align || 'center');
            numKeys.forEach(function(k) {
                var el = $('#surface_' + k);
                if (!el.is(':focus')) el.val(sf[k] === undefined ? 0 : sf[k]);
            });
            var label = 'bypass';
            if (sf.enable) {
                label = (sf.width || 0) + ' x ' + (sf.height || 0) + (sf.halfheight ? ' half' : '') + (sf.rotate ? ' ' + sf.rotate + '°' : '') + ' ' + (sf.fit || 'cover');
            }
            $('#surface_state').text(label).toggleClass('badge-success', !!sf.enable).toggleClass('badge-secondary', !sf.enable);
        }
        socket.on('settings.updated', function(msg) {
            if (msg['surface'] !== undefined) fill(msg['surface']);
        });
        function patch(obj) { trigger('surface', obj); }
        $('#surface_enable').on('change', function() { patch({ enable: this.checked }); });
        $('#surface_halfheight').on('change', function() { patch({ halfheight: this.checked }); });
        $('#surface_fit').on('change', function() { patch({ fit: this.value }); });
        $('#surface_align').on('change', function() { patch({ align: this.value }); });
        numKeys.forEach(function(k) {
            $('#surface_' + k).on('change', function() { var o = {}; o[k] = Number(this.value) || 0; patch(o); });
        });
    })();

    // --- Radar panel (biennale-2026-module-radar) ---
    // Tuning sliders + live presence feedback from the radar interface. A second
    // settings.updated handler (coexists with the one above) syncs the radar-* keys.
    (function() {
        var radarKeys = {
            'radar-range': 'radar_range', 'radar-width': 'radar_width',
            'radar-enter-ms': 'radar_enter', 'radar-leave-ms': 'radar_leave'
        };
        socket.on('settings.updated', function(msg) {
            for (var k in radarKeys) {
                if (msg[k] !== undefined) {
                    $('#' + radarKeys[k]).val(msg[k]);
                    $('#' + radarKeys[k] + '_val').text(msg[k]);
                }
            }
        });
        Object.keys(radarKeys).forEach(function(key) {
            $('#' + radarKeys[key]).on('input change', function() {
                $('#' + radarKeys[key] + '_val').text(this.value);
                trigger(key, parseInt(this.value));
            });
        });
        // live presence feedback (~5Hz from the radar interface)
        socket.on('radar-status', function(st) {
            var badge = $('#radar_state');
            panelFollow('#radar_body', st['connected']);
            if (!st['connected']) {
                badge.text('no adapter').removeClass('badge-success badge-danger').addClass('badge-secondary');
                $('#radar_presence').text('—').css('color', '');
                $('#radar_detail').text('radar not connected');
                $('#radar_live').css('background', '#eee');
                return;
            }
            badge.text('connected').removeClass('badge-secondary badge-danger').addClass('badge-success');
            var present = st['present'];
            $('#radar_presence').text(present ? 'IN ZONE' : 'clear').css('color', present ? '#1a7d4f' : '#888');
            $('#radar_live').css('background', present ? '#d6f5e6' : (st['raw'] ? '#fff6d6' : '#eee'));
            var n = st['count'] || 0;
            var d = n + ' target' + (n === 1 ? '' : 's');
            if (st['near'] != null) d += ' · nearest ' + (st['near'] / 1000).toFixed(2) + ' m';
            $('#radar_detail').text(d);
        });
    })();

    // --- Nowde panel (biennale-2026-module-radar #t-008) ---
    // ESP-NOW sync node on USB-MIDI: tunables + 1 Hz status from the nowde interface.
    (function() {
        socket.on('settings.updated', function(msg) {
            if (msg['nowde-layer'] !== undefined) $('#nowde_layer').val(msg['nowde-layer']);
            if (msg['nowde-index-default'] !== undefined) $('#nowde_index_default').val(msg['nowde-index-default']);
            if (msg['nowde-jumpfix'] !== undefined) { $('#nowde_jumpfix').val(msg['nowde-jumpfix']); $('#nowde_jumpfix_val').text(msg['nowde-jumpfix']); }
            if (msg['nowde-dance'] !== undefined) $('#nowde_dance').prop('checked', !!msg['nowde-dance']);
        });
        $('#nowde_layer').on('change', function() { trigger('nowde-layer', this.value.trim() || 'hplayer2'); });
        $('#nowde_index_default').on('change', function() { trigger('nowde-index-default', parseInt(this.value) || 0); });
        $('#nowde_jumpfix').on('input change', function() { $('#nowde_jumpfix_val').text(this.value); trigger('nowde-jumpfix', parseInt(this.value)); });
        $('#nowde_dance').on('change', function() { trigger('nowde-dance', this.checked); });

        socket.on('nowde-status', function(st) {
            var role = $('#nowde_role'), state = $('#nowde_state');
            panelFollow('#nowde_body', st['linked']);
            if (!st['linked']) {
                role.text('no node').removeClass('badge-success badge-info badge-warning').addClass('badge-secondary');
                state.text('—').removeClass('badge-success badge-danger badge-warning').addClass('badge-secondary');
                $('#nowde_media').text('—').css('color', '');
                $('#nowde_detail').text('waiting for a Nowde node…');
                $('#nowde_live').css('background', '#eee');
                return;
            }
            var r = st['role'] || 'probing';
            role.text(r.toUpperCase()).removeClass('badge-secondary badge-success badge-info badge-warning')
                .addClass(r === 'master' ? 'badge-info' : r === 'slave' ? 'badge-success' : 'badge-warning');
            var node = st['node'] || {};
            var synced = st['mesh_synced'];
            if (r === 'master') {
                var n = st['slaves'] || 0;
                state.text((synced ? 'mesh synced' : 'mesh not synced') + ' · ' + n + ' slave' + (n === 1 ? '' : 's'))
                     .removeClass('badge-secondary badge-danger badge-warning badge-success')
                     .addClass(synced && n > 0 ? 'badge-success' : synced ? 'badge-warning' : 'badge-danger');
            } else {
                state.text('v' + (node['version'] || '?') + (node['board'] ? ' · ' + node['board'] : ''))
                     .removeClass('badge-secondary badge-danger badge-warning').addClass('badge-success');
            }
            var playing = st['playing'];
            var idx = st['index'] || 0;
            $('#nowde_media').text(idx ? (playing ? '▶ ' : '■ ') + 'index ' + idx : (playing ? '▶' : '■ stopped'))
                             .css('color', playing ? '#1a7d4f' : '#888');
            $('#nowde_live').css('background', playing ? '#d6f5e6' : '#eee');
            var d = (r === 'master' ? 'sending on layer ' : 'node layer ') + (st['layer'] || '?');
            if (node['version']) d += ' · node v' + node['version'] + (node['board'] ? ' ' + node['board'] : '');
            $('#nowde_detail').text(d);
        });
    })();

    // --- Schedule panel (biennale-2026-module-radar #t-005) ---
    // RTC-gated daily playback window. The interface fails OPEN without a real
    // clock (never gates), so the panel makes that explicit rather than pretend.
    (function() {
        socket.on('settings.updated', function(msg) {
            if (msg['schedule-enable'] !== undefined) $('#schedule_enable').prop('checked', !!msg['schedule-enable']);
            if (msg['schedule-open'] !== undefined) $('#schedule_open').val(msg['schedule-open']);
            if (msg['schedule-close'] !== undefined) $('#schedule_close').val(msg['schedule-close']);
        });
        socket.on('schedule-status', function(st) {
            var rtc = $('#schedule_rtc'), status = $('#schedule_status');
            panelFollow('#schedule_body', st['rtc']);
            if (!st['rtc']) {
                rtc.text('no RTC').removeClass('badge-success').addClass('badge-warning');
                $('#schedule-panel').addClass('no-rtc');
                status.html('⚠ no RTC module — <b>restriction inactive</b>: playback is never gated without a trustworthy clock')
                      .removeClass('rtc-ok').addClass('rtc-warn');
                return;
            }
            rtc.text('RTC ok').removeClass('badge-warning').addClass('badge-success');
            $('#schedule-panel').removeClass('no-rtc');
            if (!st['enabled'])
                status.text('restriction off — always playing').removeClass('rtc-warn').addClass('rtc-ok');
            else
                status.text(st['open'] ? 'window OPEN — playing' : 'window CLOSED — silent')
                      .removeClass('rtc-warn').addClass('rtc-ok');
        });
        $('#schedule_enable').on('change', function() { trigger('schedule-enable', this.checked); });
        $('#schedule_open').on('change', function() { trigger('schedule-open', this.value); });
        $('#schedule_close').on('change', function() { trigger('schedule-close', this.value); });
    })();

    // --- DMX conduite panel (biennale-2026-module-dmx) ---
    // Self-contained: connection/meter come from the dmx interface over dedicated
    // socket events; the conduite editor targets a media path (current media by default,
    // or any file via dmxEdit(path)). Edits write the sidecar .dmx via trigger('dmx-save').
    (function() {
        var editMedia = null;    // media whose sidecar is in the textarea
        var dirty = false;
        $('#dmx_text').on('input', function() { dirty = true; });

        // protocol toggle (persisted setting, echoed back via settings.updated)
        socket.on('settings.updated', function(msg) {
            if (msg['dmx-protocol'] !== undefined) $('#dmx_protocol').val(msg['dmx-protocol']);
        });
        $('#dmx_protocol').on('change', function() { trigger('dmx-protocol', this.value); });

        function shortName(p) { return p ? p.split('/').pop() : '—'; }

        // adapter + current-media status
        socket.on('dmx-status', function(st) {
            var c = $('#dmx_conn');
            panelFollow('#dmx_body', st['connected']);
            if (st['connected'])
                c.text(shortName(st['port']) + ' · ' + st['protocol']).removeClass('badge-secondary badge-danger').addClass('badge-success');
            else
                c.text('no adapter').removeClass('badge-success badge-danger').addClass('badge-secondary');
            // auto-load the playing media's conduite when it changes and the user isn't editing
            // (straight trigger, not dmxEdit(): a media change must not unfold the card)
            if (st['media'] && st['media'] !== editMedia && !dirty)
                trigger('dmx-edit', st['media']);
        });

        // live meter (~5Hz), one bar per active channel — bars are keyed and
        // updated in place (a full rebuild at 5Hz flickers visibly)
        socket.on('dmx-levels', function(msg) {
            var m = $('#dmx_meter');
            var levels = msg['levels'] || {};
            var keys = Object.keys(levels);
            if (!keys.length) {
                m.data('sig', '').html('<span class="text-muted" style="font-size:.8em;">idle</span>');
                return;
            }
            if (m.data('sig') !== keys.join(',')) {     // channel set changed -> rebuild once
                m.data('sig', keys.join(',')).empty();
                keys.forEach(function(ch) {
                    $('<div>').attr('data-ch', ch).css({
                        'flex': '1 1 0', 'minWidth': '6px', 'maxWidth': '22px',
                        'height': '2px', 'transition': 'height .15s linear'
                    }).appendTo(m);
                });
            }
            keys.forEach(function(ch) {
                var v = levels[ch];
                m.children('[data-ch="' + ch + '"]').css({
                    'height': Math.max(2, Math.round(v / 255 * 76)) + 'px',
                    'background': msg['active'] ? '#7cc' : '#556'
                }).attr('title', 'ch ' + ch + ' = ' + v);
            });
        });

        // editor load / save
        socket.on('dmx-conduite', function(d) {
            editMedia = d['media'];
            dirty = false;
            $('#dmx_media').text(shortName(d['media']) + (d['file'] ? '' : '  (no media)'));
            $('#dmx_text').val(d['text'] || '');
            $('#dmx_errors').text('');
        });
        socket.on('dmx-saved', function(d) {
            showErrors(d['errors']);
            dirty = false;
            socket.emit('fileslist');   // refresh the tree so the DMX chip reflects the new sidecar
        });

        function showErrors(errs) {
            if (errs && errs.length)
                $('#dmx_errors').text(errs.map(function(e) { return 'line ' + e[0] + ': ' + e[1]; }).join('\n'));
            else
                $('#dmx_errors').text('');
        }

        // global: open any media's conduite in the editor (used by the file-list badge too)
        // — an explicit ask, so the card unfolds even without an adapter
        window.dmxEdit = function(path) { trigger('dmx-edit', path || ''); $('#dmx_body').collapse('show'); };

        $('#dmx_reload').click(function() { trigger('dmx-edit', editMedia || ''); });
        $('#dmx_save').click(function() {
            if (!editMedia) { $('#dmx_errors').text('no media selected — play a file or use its DMX badge'); return; }
            trigger('dmx-save', { media: editMedia, text: $('#dmx_text').val() });
        });
    })();

});