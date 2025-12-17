// These values are populated from app settings
let defaultLat = undefined;
let defaultLng = undefined;
let zoomLevel = undefined;

// Constants
const minLatitude = -180;
const minLongitude = -180;
const GPS_PRECISION = 4;
const DEPTH_PRECISION = 1;
const PLOT_X_DEFAULT = "roi_x";
const PLOT_Y_DEFAULT = "roi_y";
const MAX_SELECTABLE_IMAGES = 25;

let _binFilterMode = "timeline";

function getPage(page, queryString) {
    return window.location.pathname.replace(/[^/]+$/, page)
        + (queryString ? "?" + queryString : "");
}

function initDashboard(appSettings) {
    defaultLat = appSettings.default_latitude;
    defaultLng = appSettings.default_longitude;
    zoomLevel = appSettings.default_zoom_level;

    $('[data-toggle="tooltip"]').tooltip();

    $('.navbar-toggler').on('click', function () {
        $('.animated-burger').toggleClass('open');
    });

    // hide navbar after a bit of scrolling
    $(window).scroll(function (e) {
        var scroll = $(window).scrollTop();
        if (scroll >= 150) {
            $('.navbar').addClass("navbar-hide");
        } else {
            $('.navbar').removeClass("navbar-hide");
        }
    });

    $("#dataset-switcher").change(function () {
        location.href = getPage("timeline") + "dataset=" + $(this).val();
    });

    $("#go-to-bin").click(function () {
        goToBin($("#go-to-bid-pid").val());
    });

    $("#go-to-bid-pid").keypress(function (e) {
        if (e.which == 13 /* Enter */) {
            goToBin($(this).val());
        }
    });

    $('body').on('click', function (e) {
        var $target = $(e.target);

        if ($target.data('toggle') !== 'popover' && $target.parents('.popover').length === 0) {
            $('[data-toggle="popover"]').popover('hide');
        }
    });
}

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
function updateTimelineFilters(wrapper, initialValues) {
    var datasetFilter = $(wrapper).find(".dataset-filter");
    var instrumentFilter = $(wrapper).find(".instrument-filter");
    var tagFilter = $(wrapper).find(".tag-filter");
    var cruiseFilter = $(wrapper).find(".cruise-filter");
    var sampleTypeFilter = $(wrapper).find(".sample-type-filter");
    var applyFilters = $(wrapper).find(".apply-filters");

    var dataset = initialValues ? initialValues["dataset"] : datasetFilter.val();
    var instrument = initialValues ? initialValues["instrument"] : instrumentFilter.val();
    var cruise = initialValues ? initialValues["cruise"] : cruiseFilter.val();
    var tags = initialValues ? initialValues["tags"] : tagFilter.val().join();
    var sampleType = initialValues ? initialValues["sample_type"] : sampleTypeFilter.val();

    var selected_tags = tags == null ? [] : tags.split(",");

    if (dataset == "" && instrument == "" && cruise == "" && tags == "" && sampleType == "") {
        applyFilters.prop("disabled", true);
    } else {
        applyFilters.prop("disabled", false);
    }

    var qs = buildFilterOptionsQueryString(false, dataset, instrument, tags, cruise, sampleType);

    $.get("/api/filter_options?" + qs, function(data){
        reloadFilterDropdown(datasetFilter, data.dataset_options, dataset);
        reloadFilterDropdown(instrumentFilter, data.instrument_options, instrument, "IFCB");
        reloadFilterDropdown(cruiseFilter, data.cruise_options, cruise);
        reloadFilterDropdown(sampleTypeFilter, data.sample_type_options, sampleType);

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
    });
}

function initBinFilter(binFilterMode) {
    _binFilterMode = binFilterMode;

    updateTimelineFilters($("#SearchPopoverContent"), {
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

        $(".popover .filter-option").change(function(){
            var wrapper = $(this).closest(".filter-options");

            updateTimelineFilters(wrapper, null);
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

    var qs = buildFilterOptionsQueryString(false, dataset, instrument, tags, cruise, sampleType);

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

        location.href = getPage("bin", "bin=" + pid.trim());
    });
}

function isFilterOptionValid(val) {
    return (val != null && val != "" && val != "null");
}

function buildFilterOptionsArray(fromGlobals, dataset, instrument, tags, cruise, sampleType) {
    if (fromGlobals) {
        dataset = _dataset;
        instrument = _instrument;
        tags = _tags;
        cruise = _cruise
        sampleType = _sampleType
    }

    var args = [];
    if (isFilterOptionValid(dataset))
        args.push("dataset=" + dataset);
    if (isFilterOptionValid(instrument))
        args.push("instrument=" + instrument);
    if (isFilterOptionValid(tags) && tags.length > 0)
        args.push("tags=" + tags);
    if (isFilterOptionValid(cruise))
        args.push("cruise=" + cruise);
    if (isFilterOptionValid(sampleType))
        args.push("sample_type=" + sampleType);

    return args;
}

function buildFilterOptionsQueryString(fromGlobals, dataset, instrument, tags, cruise, sampleType) {
    var args = buildFilterOptionsArray(fromGlobals, dataset, instrument, tags, cruise, sampleType);

    return args.length == 0 ? "" : args.join("&");
}

function reloadFilterDropdown(dropdown, options, value, textPrefix) {
    dropdown.empty();
    dropdown.append($("<option value='' />"));
    for (var i = 0; i < options.length; i++) {
        var optionText = (textPrefix ? textPrefix : "") + options[i];
        var optionValue = options[i];
        var selected = optionValue == value ? "selected" : "";

        dropdown.append($("<option value='" + optionValue + "'" + selected + ">" + optionText + "</option>"));
    }
    dropdown.val(value);
}

function isFilteringUsed() {
    if (_dataset != "" && _dataset != "null")
        return true;

    if (_instrument != "" && _instrument != "null")
        return true;

    if (_tags != "" && _tags != "null")
        return true;

    if (_cruise != "" && _cruise != "null")
        return true;

    if (_sampleType != "" && _sampleType != "null")
        return true;
}

// Formats a list of Django validation errors into an <ul />
function formatValidationErrorsAsList(errors) {
    const items = [];

    for (const [field, messages] of Object.entries(errors)) {

        // Capitalize and format field name (e.g., "email_address" -> "Email Address")
        const fieldName = field.replace(/_/g, ' ').replace(/\b\w/g, c => c.toUpperCase());

        messages.forEach(message => {
            const prefix = field === "__all__" ? "" : `<strong>${fieldName}:</strong> `;

            items.push(`<li>${prefix}${message}</li>`);
        });
    }

    return "<ul class='error-list mb-0'>" + items.join() + "</ul>";
}

$(function () {
    $('#datasets-popover').popover({
        container: 'body',
        title: 'Dataset',
        html: true,
        placement: 'bottom',
        sanitize: false,
        template:  '<div class="popover" style="max-width:60%;" role="tooltip"><div class="arrow"></div><h3 class="popover-header"></h3><div class="popover-body" style="max-height:50vh; overflow-y:auto;"></div></div>'
    });

    $('#teams-popover').popover({
        container: 'body',
        title: 'Teams',
        html: true,
        placement: 'bottom',
        sanitize: false,
        template:  '<div class="popover" style="max-width:60%;" role="tooltip"><div class="arrow"></div><h3 class="popover-header"></h3><div class="popover-body" style="max-height:50vh; overflow-y:auto;"></div></div>'
    });
  })
