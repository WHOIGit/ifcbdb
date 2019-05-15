$(function(){
    $("#dataset-switcher").change(function(){
        location.href = "/" + $(this).val();
    });
})

function createMap(lat, lng) {
    var map = L.map('mapid').setView([lat, lng], 11);
    L.esri.basemapLayer('Oceans').addTo(map);
    L.esri.basemapLayer('OceansLabels').addTo(map);

    return map;
}

function padDigits(number, digits) {
    return Array(Math.max(digits - String(number).length + 1, 0)).join(0) + number;
}

function getTimelineTypeByMetric(metric) {
    if (metric == "humidity" || metric == "temperature")
        return "line";

    return "bar";
}

function getTimelineConfig() {
    return {
        responsive: true,
        displaylogo: false,
        scrollZoom: true
    };
}

function getTimelineData(data) {
    var plotlyType = getTimelineTypeByMetric(currentMetric);

    var series = {
        type: plotlyType,
        x: data["x"],
        y: data["y"],
        line: {
            color: '#17BECF'
        },
    };

    // For bar graphs with only one data point, the width of the bar needs to be set explicitly or
    //   Plotly will not render anything visible to the user. The x range on a single entry plot is
    //   set to 24hours, so the bar is set to a width of 1 hour
    if (plotlyType == "bar" && data["x"].length == 1) {
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
                text: data["y-axis"] + "<br />" + "Resolution: " + currentResolution + "<br />"
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
            }
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
    // up to a week: bin resolution
    // up to a month: hour resolution
    // up to two years: day resolution
    // more than that: week resolution

    // TODO: The values below are temporary for testing until there is a larger dataset available
    var binResolutionRange = moment.duration(1, "hours");
    var hourResolutionRange = moment.duration(6, "hours");
    var dayResolutionRange = moment.duration(1, "days");
    var weekResolutionRange = moment.duration(1, "weeks");

    startDate = moment(start);
    endDate = moment(end);
    duration = endDate.diff(startDate);

    if (duration > weekResolutionRange) {
        return "week";
    } else if (duration > dayResolutionRange) {
        return "day";
    } else if (duration > hourResolutionRange) {
        return "hour";
    }

    return "bin";
}