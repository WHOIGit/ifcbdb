// TODO: Move default location to settings
var defaultLat = 41.5507768;
var defaultLng = -70.6593102;
var minLatitude = -180;
var minLongitude = -180;
var zoomLevel = 6;
var GPS_PRECISION = 4;
var DEPTH_PRECISION = 1;
var PLOT_X_DEFAULT = "roi_x";
var PLOT_Y_DEFAULT = "roi_y";
var MAX_SELECTABLE_IMAGES = 25;
var _binFilterMode = "timeline";

$(function(){
    $("#dataset-switcher").change(function(){
        location.href = "/timeline?dataset=" + $(this).val();
    });

    $("#go-to-bin").click(function(){
        goToBin($("#go-to-bid-pid").val());
    });

    $("#go-to-bid-pid").keypress(function(e){
        if (e.which == 13 /* Enter */) {
            goToBin($(this).val());
        }
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

    var map = L.map('map-container').setView([lat, lng], zoomLevel);
    L.esri.basemapLayer('Oceans').addTo(map);
    L.esri.basemapLayer('OceansLabels').addTo(map);

    map.on("zoomend", function(e) {
        zoomLevel = this.getZoom();
    });

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

        $("#map-container .leaflet-popup-tip-container").hide()

        return popup;
    }

    return L.marker([lat, lng])
        .addTo(map)
        .bindPopup(
            "Latitude: <strong>" + parseFloat(lat).toFixed(GPS_PRECISION) + "</strong><br />" +
            "Longitude: <strong>" + parseFloat(lng).toFixed(GPS_PRECISION) + "</strong><br />" +
            "Depth: <strong>" + parseFloat(depth).toFixed(DEPTH_PRECISION) + "m</strong>"
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

function getTimelineIndicatorShape() {
    return {
        type: "line",
        yref: "paper",
        x0: _binTimestamp.utc().format(),
        y0: 0,
        x1: _binTimestamp.utc().format(),
        y1: 1,
        line: {
            color: "rgb(192, 32, 32)",
            width: 3,
            dash: "dash"
        }
    }
}

function getTimelineConfig() {
    return {
        responsive: true,
        displaylogo: false,
        scrollZoom: true,
        modeBarButtonsToRemove: [
            "sendDataToCloud",
            "hoverCompareCartesian",
            "hoverClosestCartesian",
            "toImage",
            "select2d",
            "lasso2d",
            "toggleSpikelines",
            "resetScale2d"
        ]
    };
}

function getTimelineTypeByMetric(metric) {
    if (metric == "temperature" || metric == "humidity") {
        return {
            "type": "scatter",
            "mode": "markers"
        }
    } else {
        return {
            "type": "bar",
            "mode": "markers"
        }
    }
}
function getTimelineData(data, selectedDate, resolution) {
    plotlyType = getTimelineTypeByMetric(currentMetric);

    var series = {
        type: plotlyType.type,
        mode: plotlyType.mode,
        x: data["x"],
        y: data["y"],
        line: {
            color: '#17BECF'
        },
    };

    /*
    // This fix should not be needed now that we always enforce the width of the bars on the plot
    // For bar graphs with only one data point, the width of the bar needs to be set explicitly or
    //   Plotly will not render anything visible to the user. The x range on a single entry plot is
    //   set to 24hours, so the bar is set to a width of 1 hour
    if (data["x"].length == 1) {
        series["width"] = [60*60*1000]
    }
    */

    var duration;
    switch (resolution) {
        case "week": duration = 7*24*60*60*1000; break;
        case "day": duration = 24*60*60*1000; break;
        case "hour": duration = 60*60*1000; break;
        default: /* bin */ duration = 5*60*1000; break;
    }

    series["width"] = Array(data["x"].length).fill(duration)

    return [series];
}

function getTimelineLayout(data, range, metric) {
    var layout =  {
        bargap: 0,
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

    if (_binTimestamp != null) {
        layout.shapes = [
            getTimelineIndicatorShape()
        ]
    }

    if (range !== undefined && range !== null) {
        if (range["xaxis.range[0]"] != undefined && range["xaxis.range[1]"] != undefined) {
            layout["xaxis"]["range"] = [
                range["xaxis.range[0]"],
                range["xaxis.range[1]"]
            ]
        }
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

    setYAxisRangeForMetric(layout, metric);

    return layout;
}

function setYAxisRangeForMetric(layout, metric) {
    if (metric == "concentration") {
        layout.yaxis.range = [0, 8500];
    } else if (metric == "n-triggers" || metric == "n-images") {
        layout.yaxis.range = [0, 10500];
    } else if (metric == "ml-analyzed") {
        layout.yaxis.range = [0, 5.5];
    } else if (metric == "temperature") {
        layout.yaxis.range = [0, 55];
    } else if (metric == "humidity") {
        layout.yaxis.range = [0, 120];
    } else if (metric == "size") {
	layout.yaxis.range = [0, 1024*1024*40]; // 40MB
    }
}

/*
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
*/

// Special consideration is needed to capture the width/height of the newly loaded image so that we can also
//   update the default width/height of the outline and blob images
// See: https://stackoverflow.com/questions/19122625/how-i-can-get-image-width-after-set-src-attribute-without-reload-page
function changeImage(img, src, blobImg, outlineImg){
    var blobShown = !blobImg.is(":hidden");
    var outlineShown = !outlineImg.is(":hidden");

    img.unbind("load").on('load', function() {
        $(this).show();

        blobImg.attr("src", "");
        blobImg.width(this.width);
        blobImg.height(this.height);

        outlineImg.attr("src", "");
        outlineImg.width(this.width);
        outlineImg.height(this.height);

        if (blobShown) {
            $("#detailed-image-blob-link").click();
        } else {
            blobImg.hide();
        }
        if (outlineShown) {
            $("#detailed-image-outline-link").click();
        } else {
            outlineImg.hide();
        }

        resizeMap();
    })
    .attr("src", src)
    .each(function() {
        if (this.complete) {
            $(this).trigger('load');
        }
    });
}

function buildColorArray(dataPoints, index) {
    var colors = $.map(dataPoints, function(){ return "#1f77b4"; });
    if (index >= 0 && index < dataPoints.length)
        colors[index] = "#bb0000";

    return colors;
}

function highlightSelectedBinByDate() {
    if (_binTimestamp == null)
        return;

    var timeline = $("#primary-plot-container")[0];

    _preventTimelineRelayout = true;
    Plotly.relayout(timeline, {
        shapes: [
            getTimelineIndicatorShape()
        ]
    });
}

function buildLeafletIcon(color) {
    return new L.Icon({
        iconUrl: "/static/vendor/leaflet-color-markers/img/marker-icon-" + color + ".png",
        shadowUrl: "/static/vendor/leaflet-color-markers/img/marker-shadow.png",
        iconSize: [8, 12],
        iconAnchor: [8, 12],
        popupAnchor: [-8, -12],
        shadowSize: [8, 12]
    });
}

//************* Timeline/List Filtering Methods ***********************/
function getQuerystringFromParameters(dataset, instrument, tags, cruise) {
    var parameters = []
    if (dataset != "")
        parameters.push("dataset=" + dataset);
    if (instrument != "")
        parameters.push("instrument=" + instrument);
    if (tags != "") {
        parameters.push("tags=" + tags);
    }
    if (cruise != "" ) {
        parameters.push("cruise=" + cruise);
    }

    if (parameters.length == 0)
        return "";

    return parameters.join("&");
}

function updateTimelineFilters(datasetFilter, instrumentFilter, tagFilter, cruiseFilter, sampleTypeFilter, initialValues) {

    var dataset = initialValues ? initialValues["dataset"] : datasetFilter.val();
    var instrument = initialValues ? initialValues["instrument"] : instrumentFilter.val();
    var cruise = initialValues ? initialValues["cruise"] : cruiseFilter.val();
    var tags = initialValues ? initialValues["tags"] : tagFilter.val().join();
    var sampleType = initialValues ? initialValues["sample_type"] : sampleTypeFilter.val();

    var selected_tags = tags == null ? [] : tags.split(",");

    var url = "/api/filter_options" +
        "?dataset=" + (dataset ? dataset : "") +
        "&instrument=" + (instrument ? instrument : "") +
        "&tags=" + (tags ? tags : "") + 
        "&cruise=" + (cruise ? cruise : "") +
        "&sample_type=" + (sampleType ? sampleType : "");

    $.get(url, function(data){
        datasetFilter.empty();
        datasetFilter.append($("<option value='' />"));
        for (var i = 0; i < data.dataset_options.length; i++) {
            var option = data.dataset_options[i];
            datasetFilter.append($("<option value='" + option + "'" + (option == dataset ? "selected" : "") + ">" + option + "</option>"));
        }
        datasetFilter.val(dataset);

        instrumentFilter.empty();
        instrumentFilter.append($("<option value='' />"));
        for (var i = 0; i < data.instrument_options.length; i++) {
            var option = data.instrument_options[i];
            instrumentFilter.append($("<option value='" + option + "' " + (option == instrument ? "selected" : "") + ">IFCB" + option + "</option>"));
        }
        instrumentFilter.val(instrument);

        cruiseFilter.empty();
        cruiseFilter.append($("<option value='' />"));
        for (var i = 0; i < data.cruise_options.length; i++) {
            var option = data.cruise_options[i];
            cruiseFilter.append($("<option value='" + option + "' " + (option == cruise ? "selected": "") + ">" + option + "</option>"));
        }
        cruiseFilter.val(cruise);

        tagFilter.empty();
        for (var i = 0; i < data.tag_options.length; i++) {
            var option = data.tag_options[i];

            var element = $("<option value='" + option + "'>" + option + "</option>");
            if (selected_tags.includes(option)) {
                element.attr("selected", "selected");
            }

            tagFilter.append(element);
        }

        tagFilter.trigger('chosen:updated');

        sampleTypeFilter.empty();
        sampleTypeFilter.append($("<option value='' />"));
        for (var i = 0; i < data.sample_type_options.length; i++) {
            var option = data.sample_type_options[i];
            sampleTypeFilter.append($("<option value='" + option + "' " + (option == sampleType ? "selected": "") + ">" + option + "</option>"));
        }
        sampleTypeFilter.val(cruise);
    });
}

function initBinFilter(binFilterMode) {
    _binFilterMode = binFilterMode;
    var datasetFilter = $("#SearchPopoverContent .dataset-filter");
    var instrumentFilter = $("#SearchPopoverContent .instrument-filter");
    var tagFilter = $("#SearchPopoverContent .tag-filter");
    var cruiseFilter = $("#SearchPopoverContent .cruise-filter");
    var sampleTypeFilter = $("#SearchPopoverContent .sample-type-filter");

    updateTimelineFilters(datasetFilter, instrumentFilter, tagFilter, cruiseFilter, sampleTypeFilter, {
        "dataset": _dataset,
        "instrument": _instrument,
        "tags": _tags,
        "cruise": _cruise,
        "sample_type": _sampleType
    });

    _filterPopover = $('[data-toggle="popover"]').popover({
      container: 'body',
      title: 'Update Filters',
      html: true,
      placement: 'bottom',
      sanitize: false,
      content: function () {
          return $("#SearchPopoverContent").html();
      }
    });

    _filterPopover.on('shown.bs.popover', function () {
        $(".popover .tag-filter").chosen({
            placeholder_text_multiple: "Select Tags..."
        });

        $(".popover .dataset-filter, .popover .instrument-filter, .popover .tag-filter").change(function(){
            var wrapper = $(this).closest(".filter-options");
            var datasetFilter = wrapper.find(".dataset-filter");
            var instrumentFilter = wrapper.find(".instrument-filter");
            var tagFilter = wrapper.find(".tag-filter");
            var cruiseFilter = wrapper.find(".cruise-filter");
            var sampleTypeFilter = wrapper.find(".sample-type-filter");

            updateTimelineFilters(datasetFilter, instrumentFilter, tagFilter, cruiseFilter, sampleTypeFilter, null);
        });
    });
}

function applyFilters() {
    var dataset = $(".popover .dataset-filter").val();
    var instrument = $(".popover .instrument-filter").val(); 
    var cruise = $(".popover .cruise-filter").val();
    var sampleType = $(".popover .sample-type-filter").val();
    var tags = $(".popover .tag-filter option:selected")
        .map(function() {return $(this).val()}).get()
        .join();

    var qs = getQuerystringFromParameters(dataset, instrument, tags, cruise);

    $.get("/api/bin_exists?" + qs, function(data) {
        if (!data.exists) {
            alert("No bins were found matching the specified filters. Please update the filters and try again")
            return;
        }

        _dataset = dataset;
        _instrument = instrument;
        _tags = tags;
        _cruise = cruise;
        _sampleType = sampleType;

        if (_binFilterMode == "list") {
            location.href = createListLink();
        } else {
            location.href = createBinLink(_bin);
        }
    });

    return false;
}

function goToBin(pid) {
    if (!pid || pid.trim() == "")
        return;

    $.get("/api/single_bin_exists?pid=" + pid.trim(), function(data){
        if (!data.exists) {
            alert("No matching bin was found. Please check the PID and try again");
            return;
        }

        location.href = "/bin?bin=" + pid.trim();
    });
}