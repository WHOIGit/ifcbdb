//************* Local Variables ***********************/
var _bin = ""; // Bin Id
var _dataset = ""; // Dataset Name
var _mosaicPage = 0; // Current page being displayed in the mosaic
var _mosaicPages = -1; // Total number of pages for the mosaic
var _coordinates = []; // Coordinates of images within the current mosaic
var _isMosaicLoading = false; // Whether the mosaic is in the process of loading
var _isBinLoading = false; // Whether the bin is in the process of loading
var _plotData = null; // Local storage of the current bin's plot data
var _map = null; // Current Leaflet map
var _marker = null; // Current marker shown on the map
var _workspace = "mosaic"; // The current workspace a user is seeing
var _pendingMapLocation = null; // The next map position to render (see notes in updateMapLocation)
var _csrf = null; // CSRF token from Django for post requests
var _userId = null; // Id of the currently logged in user

//************* Common Methods ***********************/

// Generates a relative link to the current bin/dataset
// TODO: Verify these URLs match the current Django routes
function createLink() {
    if (_dataset != "")
        return "/" + _dataset + "/" + _bin + ".html";

    return "/bin?id=" + _bin;
}

// Switches between workspaces: map, plot, mosaic
function showWorkspace(workspace) {
    _workspace = workspace;

    $("#image-tab-content").toggleClass("d-none", !(workspace == "mosaic"));
    //$("#mosaic-footer").toggleClass("d-none", !(workspace == "mosaic"));
    $("#plot-tab-content").toggleClass("d-none", !(workspace == "plot"));
    $("#map-tab-content").toggleClass("d-none", !(workspace == "map"));

    // After showing the map, Leaflet needs to have invalidateSize called to recalculate the
    //   dimensions of the map container (it cannot determine it when the container is hidden
    if (workspace == "map") {
        if (_map) {
            setTimeout(function() { _map.invalidateSize() }, 100);
        }

        if (_pendingMapLocation != null) {
            updateMapLocation(_pendingMapLocation);
        }
    }
}

//************* Bin Methods ***********************/
function updateBinStats(data) {
    var timestamp = moment.utc(data["timestamp_iso"]);

    $("#stat-date-time").html(
        timestamp.format("YYYY-MM-DD") + "<br />" +
        timestamp.format("HH:mm:ss z") +
        "<br /> (" + timestamp.fromNow() + ")"
    );

    $("#stat-instrument").html(data["instrument"]);
    $("#stat-num-triggers").html(data["num_triggers"]);
    $("#stat-num-images").html(data["num_images"]);
    $("#stat-trigger-freq").html(data["trigger_freq"]);
    $("#stat-ml-analyzed").html(data["ml_analyzed"]);
}

function updateBinMetadata() {
    $.get("/api/metadata/" + _bin, function(data) {
        tbody = $("#bin-metadata tbody");
        tbody.empty();

        for (key in data.metadata) {
            row = $("<tr />");
            row.append($("<td />", { "scope": "row", "text": key }))
            row.append($("<td />", { "text": data.metadata[key] }))
            tbody.append(row);
        }
    });
}

function updateBinDatasets(data) {
    $("#dataset-links").empty();

    for (var i = 0; i < data.datasets.length; i++) {
        // <a href="#" class="d-block">asdasd</a>
        $("#dataset-links").append(
            $("<a class='d-block' />")
            .attr("href", "/bin?id=" + _bin + "&dataset=" + data.datasets[i])
            .text(data.datasets[i])
        )
    }
}

function updateBinTags(data) {
    displayTags(data.tags);
    toggleTagInput(false);
}

function updateBinComments(data) {
    // TODO: Implement
    console.log(data);
}

function updateBinDownloadLinks(data) {
    $("#download-adc").attr("href", _dataset + "/" + _bin + ".adc");
    $("#download-hdr").attr("href", _dataset + "/" + _bin + ".hdr");
    $("#download-roi").attr("href", _dataset + "/" + _bin + ".roi");
    $("#download-zip").attr("href", _dataset + "/" + _bin + ".zip");
    $("#download-blobs").attr("href", _dataset + "/" + _bin + "_blob.zip");
    $("#download-features").attr("href", _dataset + "/" + _bin + "_features.csv");

    $("#download-blobs").toggle(data["has_blobs"]);
    $("#download-blobs-disabled").toggle(!data["has_blobs"]);

    $("#download-features").toggle(data["has_features"]);
    $("#download-features-disabled").toggle(!data["has_features"]);

    // TODO: Need to hook up link for "autoclass"
}

// TODO: Handle when dataset is empty
function changeToClosestBin(targetDate) {
    if (_isBinLoading || _isMosaicLoading)
        return false;

    _isBinLoading = true;
    _isMosaicLoading = true;

    var url = "/api/" + _dataset + "/closest_bin";
    $.post(url, { "target_date": targetDate }, function(resp) {
        if (resp.bin_id != "")
            changeBin(resp.bin_id, true);
    });
}

// TODO: Handle when dataset is empty
function changeToNearestBin(lat, lng) {
    if (_isBinLoading || _isMosaicLoading)
        return false;

    _isBinLoading = true;
    _isMosaicLoading = true;

    var url = "/api/nearest_bin";
    var data = {
        dataset: _dataset,
        latitude: lat,
        longitude: lng
    };

    $.post(url, data, function(resp) {
        if (resp.bin_id != "")
            changeBin(resp.bin_id, true);
    });
}

function toggleTagInput(isAdding) {
    $("#add-tag").toggleClass("d-none", isAdding)
    $("#tag-name").toggleClass("d-none", !isAdding)
    $("#tag-confirm").toggleClass("d-none", !isAdding)
    $("#tag-cancel").toggleClass("d-none", !isAdding)
}

function addTag() {
    var tag = $("#tag-name").val();
    if (tag.trim() === "")
        return;

    var payload = {
        "csrfmiddlewaretoken": _csrf,
        "tag_name": tag
    };

    $.post("/secure/api/add-tag/" + _bin, payload, function(data) {
        displayTags(data.tags);
        $("#tag-name").val("");
    });
}

function removeTag(tag) {
    if (String(tag).trim() === "")
        return;

    var payload = {
        "csrfmiddlewaretoken": _csrf,
        "tag_name": tag
    };

    $.post("/secure/api/remove-tag/" + _bin, payload, function(data) {
        displayTags(data.tags);
    });
}

function addComment() {
    // TODO: Pull actual input
    var payload = {
        "csrfmiddlewaretoken": _csrf,
        "comment": "This is a test"
    };

    // TODO: Refresh comment list and count
    $.post("/secure/api/add-comment/" + _bin, payload, function(data){
        console.log(data);
    });
}

function displayTags(tags) {
    var list = $("#tags");
    list.empty();

    for (var i = 0; i < tags.length; i++) {
        var tag = tags[i];
        var li = $("<span class='badge badge-pill badge-light mx-1'>");
        var span = li.text(tag);
        var icon = $("<i class='fas fa-trash pl-1'></i>");
        var remove = $("<a href='javascript:;' class='remove-tag' data-tag='" + tag + "' />");

        li.append(span);

        if (_userId != null) {
            li.append(remove);
            remove.append(icon);
        }

        list.append(li);
    }
}

//************* Mosaic Methods ***********************/
function delayedMosaic(page) {
    $("#mosaic").hide();
    $("#mosaic-loading").show();

    setTimeout(function() {
        loadMosaic(page);
    }, 50);
}

function rebuildMosaicPageIndexes() {
    $(".page-index").remove();
    for (var i = 0; i < _mosaicPages + 1; i++) {
        var li = $("<li class='page-item page-index' />").toggleClass("active", i == 0);
        var btn = $("<a class='page-link' />").text(i + 1).attr("data-page", i);

        li.append(btn).insertBefore($(".page-next"));
    }

    $("#bin-paging").show();
}

function enableNextPreviousBinButtons() {
    var prevBin = $("#previous-bin").data("bin");
    $("#previous-bin").toggleClass("disabled", prevBin === "");

    var nextBin = $("#next-bin").data("bin");
    $("#next-bin").toggleClass("disabled", nextBin === "");
}

function loadMosaic(pageNumber) {
    var viewSize = $("#view-size option:selected").val();
    var scaleFactor = $("#scale-factor option:selected").val();

    $("#mosaic-loading").show();
    $("#mosaic").hide();
    _coordinates = [];

    // indicate to the user that coordinates are loading
    $("#mosaic").css("cursor", "wait");

    var binDataUrl = "/api" + (_dataset != "" ? "/" + _dataset : "") + "/bin/" + _bin +
        "?view_size=" + viewSize +
        "&scale_factor=" + scaleFactor;

    $.get(binDataUrl, function(data) {

        // Update the coordinates for the image
        _coordinates = JSON.parse(data["coordinates"]);

        // Indicate to the user that the mosaic is clickable
        $("#mosaic").css("cursor", "pointer");

        // Re-enable next/previous buttons
        enableNextPreviousBinButtons();

        // Update the paging
        if (data["num_pages"] != _mosaicPages) {
            _mosaicPages = data["num_pages"];

            rebuildMosaicPageIndexes();
        }

        updateMosaicPaging();

        _isMosaicLoading = false;
    });

    // TODO: Needs error handling if mosaic cannot be generated
    var mosaicUrl = "/api/mosaic/encoded_image/" + _bin +
        "?view_size=" + viewSize +
        "&scale_factor=" + scaleFactor +
        "&page=" + pageNumber;

    $.get(mosaicUrl, function(data) {
        $("#mosaic").attr("src", "data:image/png;base64," + data);
        $("#mosaic-loading").hide();
        $("#mosaic").show();
    });
}

function changeMosaicPage(pageNumber) {
    _mosaicPage = pageNumber;

    delayedMosaic(pageNumber);
    updateMosaicPaging();
}

function updateMosaicPaging() {
    $(".page-previous").toggleClass("disabled", (_mosaicPage <= 0));
    $(".page-next").toggleClass("disabled", (_mosaicPage >= _mosaicPages));

    $.each($(".page-index a"), function() {
        var isSelected = $(this).data("page") == _mosaicPage;

        $(this).closest("li").toggleClass("active", isSelected);
    });

    $("#bin-paging").show();
}

//************* Map Methods ***********************/
function updateMapLocation(data) {
    if (!_map) {
        _map = createMap(data.lat, data.lng);
        _map.on("click", function(e) {
            changeToNearestBin(e.latlng.lat, e.latlng.lng);
        });
    }

    _marker = changeMapLocation(_map, data.lat, data.lng, data.depth, _marker);
    _pendingMapLocation = null;
}

//************* Plotting Methods  ***********************/
function updatePlotVariables(plotData) {
    var plotXAxis = $("#plot-x-axis");
    var plotYAxis = $("#plot-y-axis");
    var selectedX = plotXAxis.val();
    var selectedY = plotYAxis.val();

    plotXAxis.empty();
    plotYAxis.empty();

    var keys = [];
    $.each(plotData, function(key) {
        keys.push(key);
        plotXAxis.append($("<option />").text(key));
        plotYAxis.append($("<option />").text(key));
    });

    plotXAxis.val(keys.includes(selectedX) ? selectedX : PLOT_X_DEFAULT);
    plotYAxis.val(keys.includes(selectedY) ? selectedY : PLOT_Y_DEFAULT);
}

function initPlotData() {
    $.get("/api/plot/" + _bin, function(data) {
        _plotData = data;

        var plotXAxis = $("#plot-x-axis");
        var plotYAxis = $("#plot-y-axis");

        updatePlotVariables(data);

        plotXAxis.val(PLOT_X_DEFAULT);
        plotYAxis.val(PLOT_Y_DEFAULT);

        updatePlot();
    });
}

function updatePlotData() {
    // TODO: The plot container has a hard coded height on it that we should make dynamic. However, doing so causes
    //   the plot, when rendering a second time, to revert back to the minimum height
    $.get("/api/plot/" + _bin, function(data) {
        _plotData = data;

        updatePlotVariables(data);

        updatePlot();
    });
}

//************* Timeline Methods ***********************/

//************* Events ***********************/
function initEvents() {

    // Restore the last bin back to the stack
    $(window).on("popstate", function(e) {
        var state = e.originalEvent.state;

        changeBin(state["bin_id"], false);
    });

    // Open the share dialog window
    $("#share-button").click(function(e) {
        e.preventDefault();

        var link = $("#share-link");
        var base = link.data("scheme") + "://" + link.data("host");

        $("#share-modal").modal();
        $("#share-link").val(base + createLink()).select();
    });

    // Copy the share link to the clipboard
    $("#copy-share-link").click(function(e) {
        e.preventDefault();

        $("#share-link").select();
        document.execCommand("Copy");
    });

    // Prevent users from clicking while the bin page is loading
    $("#bin-header").click(function() {
        $("#bin-header").css("pointer-events", "none");
    });

    // Changing the view size of the mosaic
    $("#view-size").change(function() {
        var viewSize = $("#view-size").val();
        var vs = viewSize.split("x");
        var height = parseInt(vs[1]);

        $('#mosaic-loading').height(height);

        changeBin(_bin, true);
    });

    // Changing the scale factor for the mosaic
    $("#scale-factor").change(function(e) {
        changeBin(_bin, true);
    });

    // Bin navigation (next/prev)
    $("#previous-bin, #next-bin").click(function(e) {
        e.preventDefault();

        changeBin($(this).data("bin"), true);
    });

    // Mosaic paging
    $("#bin-paging")
        .on("click", ".page-previous", function(e) {
            e.preventDefault();

            if (_mosaicPage > 0)
                changeMosaicPage(_mosaicPage - 1);
        })
        .on("click", ".page-next", function(e) {
            e.preventDefault();

            if (_mosaicPage < _mosaicPages)
                changeMosaicPage(_mosaicPage + 1);
        })
        .on("click", ".page-index a", function(e) {
            e.preventDefault();

            var pageNumber = $(this).data("page")

            changeMosaicPage(pageNumber);
        });

    // Changing the metric shown on the timeline
    $("#ts-tabs .nav-link").click(function() {
        var metric = $(this).data("metric");

        timelineValid = false;
        timelineWaiting = false;
        createTimeSeries(metric);
    });

    // Showing the plot workspace
    $("#show-plot").click(function(e) {
        showWorkspace("plot");
    });

    // Showing the mosaic workspace
    $("#show-mosaic").click(function(e) {
        showWorkspace("mosaic");
    });

    // Showing the map workspace
    $("#show-map").click(function(e) {
        showWorkspace("map");
    });

    // Add a tag to a bin
    $("#add-tag").click(function(e) {
        toggleTagInput(true);
        $("#tag-name").focus();
    });

    $("#tag-cancel").click(function(e) {
        toggleTagInput(false);
    });

    $("#tag-confirm").click(function(e) {
        addTag();
    });

    $("#tag-name").on("keyup", function(e) {
        if (e.keyCode == 13) {
            addTag();
        }
    });

    // Remove a tag from a bin
    $("#tags").on("click", ".remove-tag", function(e) {
        removeTag($(this).data("tag"));
    });

    $(".show-metadata").click(function(e){
        $("#metadata-header").toggleClass("d-none", false);
        $("#comments-header").toggleClass("d-none", true);
        $("#metadata-panel").toggleClass("d-none", false);
        $("#comments-panel").toggleClass("d-none", true);
    });

    $(".show-comments").click(function(e){
        $("#metadata-header").toggleClass("d-none", true);
        $("#comments-header").toggleClass("d-none", false);
        $("#metadata-panel").toggleClass("d-none", true);
        $("#comments-panel").toggleClass("d-none", false);
    });

    $("#confirm-comment").click(function(e){
        addComment();
    });
}

//************* Initialization methods and page hooks ***********************/
$(function() {

    // Misc UI elements based on constants
    $("#max-images").text(MAX_SELECTABLE_IMAGES);

    initEvents();

    initPlotData();
});