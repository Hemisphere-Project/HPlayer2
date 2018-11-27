$(document).ready(function() {


    /*
     *  SOCKETIO
     */

    var socket = io.connect(location.protocol + '//' + document.domain + ':' + location.port);
    var settings;
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
    });

    socket.on('files', function(msg) {

        console.log(msg)

        $('#trees').empty()

        msg.forEach(function(element) {
          var col = $('<div class="col-xl-6 col-lg-12 col-md-12 col-sm-12 " />').appendTo($('#trees'))
          var head = $('<div class="card-header text-white bg-dark">').html('<span>'+element['path']+'</span>').appendTo(col)
            $('<span class="badge badge-info float-right">upload</span>').appendTo(head).on('click', function(){
              $('#uploadModal').modal()
            })
          var tree = $('<div class="tree mb-3" />').appendTo(col)
          // $('<br />').appendTo($('#trees'))

          tree.treeview({
            data: element['nodes'],
            selectable: true,
            multiSelect: true,
            color: "#000000"
          });
          tree.on('nodeSelected', function(event, data) {
            // console.log(event, data)
          });
        });

/*

.

        $('#tree').treeview({
          data: msg,
          selectable: true,
          multiSelect: true,
          color: "#000000"
        });

        $('#tree').on('nodeSelected', function(event, data) {
          // console.log(event, data)
        });

        if(msg !== null && msg.length > 0) {
          $('#delete_btn').show()
          $('#empty-tree').hide()
        }
        else {
          $('#delete_btn').hide()
          $('#empty-tree').show()
        }
        */
    });

    socket.on('status', function(msg) {
        // console.log(msg)
        var str_msg = JSON.stringify(msg)
        $('#log1').text(str_msg)

        if (last_status_str != str_msg) {

          setBtnClass('#play_btn', 'success', msg['isPlaying'])
          setBtnClass('#pause_btn', 'warning', msg['isPaused'])

          $('#media_name').text(msg['media'])
          $('#time_ellapsed').text(msg['time'])

          last_status = msg
          last_status_str = str_msg

          $("button").blur();
        }

    });

    socket.on('settings', function(msg) {
        // console.log(msg)
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

        $("button").blur();

        settings = msg
    });

    // Handlers for the different forms in the page.
    // These accept data from the user and send it to the server in a
    // variety of ways
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
    $('.vol-main').on('click', function(event) {
      $('.vol-more').toggle()
    });
    $('.vol-more').hide()


    // Files uploader
    $("#drop-area").dmUploader({
      url: '/upload',
      queue: true,
      //extFilter: ["jpg", "jpeg", "png", "gif"],

      onInit: function(){
        console.log('Callback: Plugin initialized');
        $('#upload-list').hide()
      },

      onNewFile: function(id){
        $('#upload-list').show()
      }
      // ... More callbacks
    });

    $('#delete_btn').click(function(event) {
        var selected = []
        $(".tree").each(function( index ) {
          selected.push.apply(selected, $( this ).treeview('getSelected'))
        });
        var r = confirm("Are you sure ?!");
        if (r == true) socket.emit('filesdelete', selected)
    });
    $('#playsel_btn').click(function(event) {
        var selected = []
        $(".tree").each(function( index ) {
          selected.push.apply(selected, $( this ).treeview('getSelected'))
        });
        socket.emit('playlist', selected)
    });
});
