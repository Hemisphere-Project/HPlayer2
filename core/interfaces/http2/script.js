  var settings;
  var playlist;

  var socket = io.connect(location.protocol + '//' + document.domain + ':' + location.port);
  var last_status;
  var last_status_str;

  function setBtnClass(sel, style, active) {
    if (active) {
      $(sel).addClass('btn-'+style)
      $(sel).removeClass('btn-outlined-'+style)
    }
    else {
      $(sel).removeClass('btn-'+style)
      $(sel).addClass('btn-outlined-'+style)
    }
  }

  /*
    SOCKETIO
  */

  socket.on('connect', function() {
      console.log('SocketIO connected :)')
      socket.emit('fileslist');
      $('#link-connected').show();
      $('#link-disconnected').hide();
  });

  socket.on('disconnect', function() {
      console.log('SocketIO disconnected :(')
      $('#link-connected').hide();
      $('#link-disconnected').show();
  });

  socket.on('name', function(name) {
      console.log('Player name:', name)
      $('#playerName').html(name);
      document.title = name+' | HPlayer2'
  });

  socket.on('files', function(msg) {

      $('#trees').empty()

      msg.forEach(function(element) {
        var col = $('<div class="col-xl-12 col-lg-12 col-md-12 col-sm-12 " />').appendTo($('#trees'))
        var head = $('<div class="card-header text-white bg-dark filesBar">').html('<span>'+element['path']+'</span>').appendTo(col)
          var upload = $('<span class="badge badge-info float-right">upload</span>').appendTo(head).on('click', function(){
            $('#uploadModal').modal()
          })

        var tree = $('<div class="tree mb-3" id="filestree" />').appendTo(col)
        // $('<br />').appendTo($('#trees'))

        tree.treeview({
          data: element['nodes'],
          selectable: true,
          multiSelect: true,
          color: "#000000",
          showTags: true
        });
        tree.on('nodeSelected', function(event, data) {
          // console.log(event, data)
        });
        console.log('Files loaded')
        // tree.treeview('collapseAll')
      });
  });

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

        setBtnClass('#play_btn', 'success', msg['isPlaying'])
        setBtnClass('#pause_btn', 'warning', msg['isPaused'])

        $('#media_name').text(msg['media'])
        playlistMedia()

        $("button").blur();
      }
      
  });

  socket.on('settings', function(msg) {
      
      //console.log(msg)
      var str_msg = JSON.stringify(msg)
      $('#log2').text(str_msg)

      setBtnClass('#loopAll_btn', 'info', (msg['loop'] == 2))
      setBtnClass('#loopOne_btn', 'info', (msg['loop'] == 1))
      setBtnClass('#mute_btn', 'warning', msg['mute'])
      setBtnClass('#auto_btn', 'secondary', msg['autoplay'])

      $('#volume_range').val(msg['volume'])
      $('#volumeMain').html(msg['volume'])

      $('#left_range').val(msg['pan'][0])
      $('#volumeLeft').html(msg['pan'][0])

      $('#right_range').val(msg['pan'][1])
      $('#volumeRight').html(msg['pan'][1])
      
      $('#audiomode_mono').prop( "checked", (msg['audiomode'] == 'mono') )

      playlistUpdate(msg['playlist'])

      $("button").blur();

      settings = msg
  });

  /*
    PLAYBACK
  */

  $('#play_btn').click(function(event) {
    if(!last_status['isPaused']) socket.emit('play');
    else socket.emit('resume');
  });
  $('#pause_btn').click(function(event) {
    if(!last_status['isPaused']) socket.emit('pause');
    else socket.emit('resume');
  });
  $('#prev_btn').click(function(event) {
      socket.emit('prev');
  });
  $('#next_btn').click(function(event) {
      socket.emit('next');
  });
  $('#stop_btn').click(function(event) {
      socket.emit('stop');
  });
  $('#loopAll_btn').click(function(event) {
    if(settings['loop'] != 2) socket.emit('loop', 'all');
    else socket.emit('unloop');
  });
  $('#loopOne_btn').click(function(event) {
    if(settings['loop'] != 1) socket.emit('loop', 'one');
    else socket.emit('unloop');
  });
  $('#mute_btn').click(function(event) {
    if(!settings['mute']) socket.emit('mute');
    else socket.emit('unmute');
  });
  $('#auto_btn').click(function(event) {
    if(!settings['autoplay']) socket.emit('autoplay');
    else socket.emit('notautoplay');
  });
  $('#reboot_btn').click(function(event) {
    var r = confirm("Reboot the device ?");
    if (r == true) socket.emit('reboot');
  });

  $('#volume_range').on('input', function(event) {
    socket.emit('volume', this.value);
  });
  $('#left_range').on('input', function(event) {
    socket.emit('pan', [this.value, $('#right_range').val()]);
  });
  $('#right_range').on('input', function(event) {
    socket.emit('pan', [$('#left_range').val(), this.value]);
  });
  $('#audiomode_mono').on('change', function(event) {
    if ($('#audiomode_mono').prop('checked')) 
      socket.emit('audiomode', 'mono');
    else
      socket.emit('audiomode', 'stereo');
  });
  $('.vol-main').on('click', function(event) {
    $('.vol-more').toggle()
  });
  $('.vol-more').hide()


  /*
    SELECTION
  */

  $('#delsel_btn').click(function(event) {
      var selected = []
      $(".tree").each(function( index ) {
        $( this ).treeview('getSelected').forEach(function(el){
          selected.push(el.path)
        })
      });
      var r = confirm("Are you sure ?!");
      if (r == true) {
        socket.emit('filesdelete', selected)
        $(".tree").each(function( index ) { $( this ).treeview('unselectAll') });
      }
  });
  $('#playsel_btn').click(function(event) {
      var selected = []
      $(".tree").each(function( index ) {
        $( this ).treeview('getSelected').forEach(function(el){
          selected.push(el.path)
        })
      });
      socket.emit('add', selected)
      $(".tree").each(function( index ) { $( this ).treeview('unselectAll') });
  });
  $('#selall_btn').click(function(event) {
      $(".tree").each(function( index ) {
        $( this ).treeview('selectAll')
      });
  });

  $('#selnone_btn').click(function(event) {
      $(".tree").each(function( index ) {
        $( this ).treeview('unselectAll')
      });
  });

  /*
    PLAYLIST
  */
  $('#clear_btn').click(function(event) {
      socket.emit('clear')
  });

  playlistAdd = function(path) {
    socket.emit('add', path)
    return false;
  };

  playlistRemove = function(path) {
    socket.emit('remove', path)
    return false;
  };

  playlistMedia = function() {
    $('#playlist').treeview('getNodes').forEach(function(node){
      if (last_status && (node.nodeId == last_status['index'])) node.backColor = "#343"
      else node.backColor = "#333"
    });
    $('#playlist').treeview('render')
  }

  playlistUpdate = function(msg) {
    var liste = [];
    if (msg)
    msg.forEach(function(el){

      var txt = el+'<div class="media-edit float-right">'
      txt += ' <span class="badge badge-danger" onClick="playlistRemove(\''+liste.length+'\'); event.stopPropagation();"> <i class="fas fa-ban"></i> </span>'
      txt += '</div>'

      liste.push({
        text:txt,
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
      socket.emit('play', {index: data.nodeId});
    });

    playlistMedia()
  }

  /* Direct Play */
  play = function(path) { 
    socket.emit('play', {path: path});
  };

  /* INTERFACES */
  $('#advancedLink').click( () => { window.location.href = '/advanced'; });
  $('#simpleLink').click( () => { window.location.href = '/simple'; });
  $('#playerLink').click( () => { window.location.href = '/player'; });

