// TODO: Move default location to settings
var defaultLat = 41.5507768;
var defaultLng = -70.6593102;
var minLatitude = -180;
var minLongitude = -180;
var zoomLevel = 6;

$(function(){
    $("#dataset-switcher").change(function(){
        location.href = "/" + $(this).val();
    });
})

function isKnownLocation(lat, lng) {
    return parseFloat(lat) >= minLatitude && parseFloat(lng) >= minLongitude;
}

function createMap(lat, lng) {
    // Center the map on the default location if the bin doesn't have real gps coordinates
    if (!isKnownLocation(lat, lng)) {
        lat = defaultLat;
        lng = defaultLng;
    }

    var map = L.map('mapid').setView([lat, lng], zoomLevel);
    L.esri.basemapLayer('Oceans').addTo(map);
    L.esri.basemapLayer('OceansLabels').addTo(map);

    return map;
}

function addMapMarker(map, lat, lng, depth) {
    // If the bin's location is not known, display a message saying so
    if (!isKnownLocation(lat, lng)) {
        var options = {
            closeButton: false,
            closeOnClick: false,
            closeOnEscapeKey: false,
            keepInView: true
        }
        var popup = L.popup(options)
            .setLatLng([defaultLat, defaultLng])
            .setContent("Unknown Location")
            .openOn(map)

        $("#mapid .leaflet-popup-tip-container").hide()
        return popup;
    }

    return L.marker([lat, lng])
        .addTo(map)
        .bindPopup(
            "Latitude: <strong>" + lat + "</strong><br />" +
            "Longitude: <strong>" + lng + "</strong><br />" +
            "Depth: <strong>" + parseFloat(depth).toFixed(1) + "m</strong>"
        )
        .openPopup();
}

function changeMapLocation(map, lat, lng, depth, existingMarker) {
    if (existingMarker) {
        map.removeLayer(existingMarker);
    }

    // Center the map on the default location if the bin doesn't have real gps coordinates
    if (isKnownLocation(lat, lng)) {
       map.setView([lat, lng], zoomLevel);
    } else {
        map.setView([defaultLat, defaultLng], zoomLevel);
    }

    return addMapMarker(map, lat, lng, depth);
}

function padDigits(number, digits) {
    return Array(Math.max(digits - String(number).length + 1, 0)).join(0) + number;
}

function getTimelineConfig() {
    return {
        responsive: true,
        displaylogo: false,
        scrollZoom: true
    };
}

function getTimelineData(data, selectedDate) {
    var series = {
        type: "bar",
        x: data["x"],
        y: data["y"],
        line: {
            color: '#17BECF'
        },
    };

    if (selectedDate != null) {
        var idx = getDataPointIndex(data.x, selectedDate);
        var colors = buildColorArray(data.x, idx);

        series["marker"] = {
            color: colors
        }
    }

    // For bar graphs with only one data point, the width of the bar needs to be set explicitly or
    //   Plotly will not render anything visible to the user. The x range on a single entry plot is
    //   set to 24hours, so the bar is set to a width of 1 hour
    if (data["x"].length == 1) {
        series["width"] = [60*60*1000]
    }

    return [series];
}

function getTimelineLayout(data, range) {
    var layout =  {
        bargap: .05,
        margin: {
            l: 75,
            r: 50,
            b: 50,
            t: 00,
            pad: 2
        },
        yaxis: {
            title: {
                text: data["y-axis"] + "<br />" + "Resolution: " + data["resolution"] + "<br />"
            },
            fixedrange: true,
        },
        "xaxis": {
            showspikes: true,
            spikethickness: 1,
            spikedash: "solid",
            spikemode: "across+toaxis",
            spikesnap: "cursor",
            spikecolor: "#000"
        },
        "marker": {
            "line": {
                "width": 10
            },
            "color": "#0f0"
        }
    };

    if (range !== undefined) {
        layout["xaxis"]["range"] = [
            range["xaxis.range[0]"],
            range["xaxis.range[1]"]
        ]
    }

    // TODO: Special handling is needed when there is only one datapoint
    //   Go through to finer resolutions until we find one with more data
    //   If we get to a case where there is just a single bin, force a 24 hour xrange
    if (data["x"].length == 1) {
        layout["xaxis"]["range"] = [
            data["x-range"]["start"],
            data["x-range"]["end"]
        ]
    }

    return layout;
}

function parseAndCalcResolution(plotlyData) {
    var start = plotlyData["xaxis.range[0]"];
    var end = plotlyData["xaxis.range[1]"];

    return calcResolution(start, end);
}

function calcResolution(start, end) {
    var hourResolutionRange = moment.duration(1, "week");
    var dayResolutionRange = moment.duration(2, "months");
    var weekResolutionRange = moment.duration(3, "years");

    startDate = moment(start);
    endDate = moment(end);
    duration = endDate.diff(startDate);

    var resolution = "";
    if (duration > weekResolutionRange) {
        resolution = "week";
    } else if (duration > dayResolutionRange) {
        resolution = "day";
    } else if (duration > hourResolutionRange) {
        resolution = "hour";
    } else {
        resolution = "bin";
    }

    return resolution;
}

// Special consideration is needed to capture the width/height of the newly loaded image so that we can also
//   update the default width/height of the outline and blob images
// See: https://stackoverflow.com/questions/19122625/how-i-can-get-image-width-after-set-src-attribute-without-reload-page
function changeImage(img, src, blobImg, outlineImg){
    blobImg.hide();
    outlineImg.hide();

    img.on('load', function() {
        blobImg.attr("src", "");
        blobImg.width(this.width);
        blobImg.height(this.height);

        outlineImg.attr("src", "");
        outlineImg.width(this.width);
        outlineImg.height(this.height);
    })
    .attr("src", src)
    .show()
    .each(function() {
        if (this.complete)
            $(this).trigger('load');
    });
}

function buildColorArray(dataPoints, index) {
    var colors = $.map(dataPoints, function(){ return "#1f77b4"; });
    if (index >= 0 && index < dataPoints.length)
        colors[index] = "#bb0000";

    return colors;
}

function getDataPointIndex(dataPoints, selectedDate) {
    var idx;
    for (idx = 0; idx < dataPoints.length; idx++) {
        if (moment(dataPoints[idx]) > selectedDate)
            break;
    }

    return idx - 1;
}

function highlightSelectedBinByIndex(dataPoints, index) {
    $("#ts-data .tab-pane").each(function(){
        var plot = $(".ts-plot-container", $(this))[0]
        if (!plot.data)
            return;

        Plotly.restyle(plot, {
            "marker": {
                "color": buildColorArray(dataPoints, index)
            }
        });
    })
}

function highlightSelectedBinByDate(dataPoints, selectedDate) {
    var idx = getDataPointIndex(dataPoints, selectedDate);
    highlightSelectedBinByIndex(dataPoints, idx);
}