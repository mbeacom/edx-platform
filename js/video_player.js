// Things to abstract out to another file

function getCookie(name) {
    var cookieValue = null;
    if (document.cookie && document.cookie != '') {
	var cookies = document.cookie.split(';');
	for (var i = 0; i < cookies.length; i++) {
	    var cookie = jQuery.trim(cookies[i]);
	    // Does this cookie string begin with the name we want?
	    if (cookie.substring(0, name.length + 1) == (name + '=')) {
		cookieValue = decodeURIComponent(cookie.substring(name.length + 1));
		break;
	    }
	}
    }
    return cookieValue;
}

function postJSON(url, data, callback) {
    $.ajax({type:'POST',
	    url: url,
		dataType: 'json',
		data: data,
		success: callback,
		headers : {'X-CSRFToken':getCookie('csrftoken')}
  });
}

// For easy embedding of CSRF in forms
$(function() {
    $('#csrfmiddlewaretoken').attr("value", getCookie('csrftoken'))
});

// For working with circuits in wiki: 

function submit_circuit(circuit_id) {
    $("input.schematic").each(function(index,element){ element.schematic.update_value(); });
    postJSON('/save_circuit/'+circuit_id, 
	     {'schematic': $('#schematic_'+circuit_id).attr("value")}, 
	     function(data){ if (data.results=='success') alert("Saved");});
    return false;
}

// Video player

var load_id = 0;

var video_speed = 1.0;

var updateytPlayerInterval;
var ajax_videoInterval;

function change_video_speed(speed, youtube_id) {
    new_position = ytplayer.getCurrentTime() * video_speed / speed;
    video_speed = speed;
    ytplayer.loadVideoById(youtube_id, new_position);    
}

function caption_at(index) {
    if (captions==0)
	return "&nbsp;";

    text_array=captions.text

    if ((index>=text_array.length) || (index < 0))
	return "&nbsp;";
    return text_array[index];
}

function caption_time_at(index) {
    if (captions==0)
	return 0;

    time_array=captions.start;

    if (index < 0)
	return 0;
    if (index>=time_array.length)
	return ytplayer.getDuration();

    return time_array[index] / 1000.0 / video_speed;
}

function caption_index(now) {
    // Returns the index of the current caption, given a time
    now = now * video_speed;

    if (captions==0)
	return 0;

    time_array=captions.start

    // TODO: Bisection would be better, or something incremental
    var i; 
    for(i=0;i<captions.start.length; i++) {
	if(time_array[i]>(now*1000)) {
	    return i-1;
	}
    }
    return i-1;
}

function format_time(t)
{
    seconds = Math.round(t);
    minutes = Math.round(seconds / 60);
    hours = Math.round(minutes / 60);
    seconds = seconds % 60;
    minutes = minutes % 60;
    return hours+":"+((minutes < 10)?"0":"")+minutes+":"+((seconds < 10)?"0":"")+(seconds%60);
}

function update_captions(t) {
    var i=caption_index(t);
    $("#vidtime").html(format_time(ytplayer.getCurrentTime())+'/'+format_time(ytplayer.getDuration()));
    var j;
    for(j=1; j<9; j++) {
	$("#std_n"+j).html(caption_at(i-j));
	$("#std_p"+j).html(caption_at(i+j));
    }
    $("#std_0").html(caption_at(i));
}

function title_seek(i) {
    // Seek video forwards or backwards by i subtitles
    current=caption_index(getCurrentTime());
    new_time=caption_time_at(current+i);
    
    ytplayer.seekTo(new_time, true);
}

function updateHTML(elmId, value) {
    document.getElementById(elmId).innerHTML = value;
}

function setytplayerState(newState) {
    //    updateHTML("playerstate", newState);
}

// Updates server with location in video so we can resume from the same place
// IMPORTANT TODO: Load test
// POSSIBLE FIX: Move to unload() event and similar
var ajax_video=function(){};

function onYouTubePlayerReady(playerId) {
    ytplayer = document.getElementById("myytplayer");
    updateytplayerInfoInterval = setInterval(updateytplayerInfo, 500);
    ajax_videoInterval = setInterval(ajax_video,5000);
    ytplayer.addEventListener("onStateChange", "onytplayerStateChange");
    ytplayer.addEventListener("onError", "onPlayerError");
    if((typeof load_id != "undefined") && (load_id != 0)) {
	var id=load_id;
	loadNewVideo(id, 0);
    }

}

// clear pings to video status when we switch to a different sequence tab with ajax
function videoDestroy() {
    load_id = 0;
    clearInterval(updateytplayerInfoInterval);
    clearInterval(ajax_videoInterval);
    ytplayer = false;
}

function log_event(e, d) {
    //$("#eventlog").append("<br>");
    //$("#eventlog").append(JSON.stringify(e));

    // TODO: Decide if we want seperate tracking server. 
    // If so, we need to resolve: 
    // * AJAX from different domain (XMLHttpRequest cannot load http://localhost:7000/userlog. Origin http://localhost:8000 is not allowed by Access-Control-Allow-Origin.)
    // * Verifying sessions/authentication

    /*window['console'].log(JSON.stringify(e));*/
    $.get("/event", 
	  {
	      "event_type" : e, 
		  "event" : JSON.stringify(d),
		  "page" : document.URL
		  },
	  function(data) {
	  });
}

function seek_slide(type,oe,value) {
    //log_event('video', [type, value]);
    if(type=='slide') {
	 // HACK/TODO: Youtube recommends this be false for slide and true for stop.
	 // Works better on my system with true/true. 
	 // We should test both configurations on low/high bandwidth 
	 // connections, and different browsers
	 // One issue is that we query the Youtube window every 250ms for position/state
	 // With false, it returns the old one (ignoring the new seek), and moves the
         // scroll bar to the wrong spot. 
	ytplayer.seekTo(value, true);
    } else if (type=='stop') {
	ytplayer.seekTo(value, true);
	log_event('video', [type, value]);
    }

    update_captions(value);
}

function get_state() {
    if (ytplayer)
	return [ytplayer.getPlayerState(),
		ytplayer.getVideoUrl(),
		ytplayer.getDuration(), ytplayer.getCurrentTime(), 
		ytplayer.getVideoBytesLoaded(), ytplayer.getVideoBytesTotal(), 
		ytplayer.getVideoStartBytes(), 
		ytplayer.getVolume(),ytplayer.isMuted(),
		ytplayer.getPlaybackQuality(),
		ytplayer.getAvailableQualityLevels()];
    return [];
}

function onytplayerStateChange(newState) {
    setytplayerState(newState);
    log_event('video', ['State Change',newState, get_state()]);
}

function onPlayerError(errorCode) {
    alert("An error occured: " + errorCode);
}

function updateytplayerInfo() {
    if(ytplayer.getPlayerState()!=3) {
	$("#slider").slider("option","max",ytplayer.getDuration());
	$("#slider").slider("option","value",ytplayer.getCurrentTime());
    }
    if (getPlayerState() == 1){
	update_captions(getCurrentTime());
    }

    //    updateHTML("videoduration", getDuration());
    //    updateHTML("videotime", getCurrentTime());
    //    updateHTML("startbytes", getStartBytes());
    //    updateHTML("volume", getVolume());
}

// functions for the api calls
function loadNewVideo(id, startSeconds) {
    captions={"start":[0],"end":[0],"text":["Attempting to load captions..."]};
    $.getJSON("/static/subs/"+id+".srt.sjson", function(data) {
        captions=data;
    });
    load_id = id;
    //if ((typeof ytplayer != "undefined") && (ytplayer.type=="application/x-shockwave-flash")) {
    // Try it every time. If we fail, we want the error message for now. 
    // TODO: Add try/catch
    try {
	ytplayer.loadVideoById(id, parseInt(startSeconds));
        load_id=0;
    }
    catch(e) {
	window['console'].log(JSON.stringify(e));
    }
}

function cueNewVideo(id, startSeconds) {
    if (ytplayer) {
	ytplayer.cueVideoById(id, startSeconds);
    }
}

function play() {
    if (ytplayer) {
	ytplayer.playVideo();
    }
}

function pause() {
    if (ytplayer) {
	ytplayer.pauseVideo();
    }
}

function stop() {
    if (ytplayer) {
	ytplayer.stopVideo();
    }
}

function getPlayerState() {
    if (ytplayer) {
	return ytplayer.getPlayerState();
    }
}

function seekTo(seconds) {
    if (ytplayer) {
	ytplayer.seekTo(seconds, true);
    }
}

function getBytesTotal() {
    if (ytplayer) {
	return ytplayer.getVideoBytesTotal();
    }
}

function getCurrentTime() {
    if (ytplayer) {
	return ytplayer.getCurrentTime();
    }
}

function getDuration() {
    if (ytplayer) {
	return ytplayer.getDuration();
    }
}

function getStartBytes() {
    if (ytplayer) {
	return ytplayer.getVideoStartBytes();
    }
}

function mute() {
    if (ytplayer) {
	ytplayer.mute();
    }
}

function unMute() {
    if (ytplayer) {
	ytplayer.unMute();
    }
}

function getEmbedCode() {
    alert(ytplayer.getVideoEmbedCode());
}

function getVideoUrl() {
    alert(ytplayer.getVideoUrl());
}

function setVolume(newVolume) {
    if (ytplayer) {
	ytplayer.setVolume(newVolume);
    }
}

function getVolume() {
    if (ytplayer) {
	return ytplayer.getVolume();
    }
}

function clearVideo() {
    if (ytplayer) {
	ytplayer.clearVideo();
    }
}