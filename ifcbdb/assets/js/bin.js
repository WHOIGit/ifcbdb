//************* Local Variables ***********************/
var _bin = "";                  // Bin Id
var _dataset = "";              // Dataset Name
var _mosaic_page = 0;           // Current page being displayed in the mosaic
var _mosaic_pages = -1;         // Total number of pages for the mosaic
var _coordinates = [];          // Coordinates of images within the current mosaic
var _isMosaicLoading = false;   // Whether the mosaic is in the process of loading
var _isBinLoading = false;      // Whether the bin is in the process of loading
var _plotData = null;           // Local storage of the current bin's plot data

//************* Common Methods ***********************/

// Generates a relative link to the current bin/dataset
// TODO: Verify these URLs match the current Django routes
function createLink() {
    if (_dataset != "")
        return  "/dataset/" +_dataset + "?bin_id=" + _bin;

    return "/bin/" + _bin + ".html";
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
    $.post(url, {"target_date": targetDate}, function(resp){
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

    $.post(url, data, function(resp){
        if (resp.bin_id != "")
            changeBin(resp.bin_id, true);
    });
}

//************* Mosaic Methods ***********************/
function delayedMosaic(page) {
    $("#mosaic").hide();
    $("#mosaic-loading").show();

    setTimeout(function(){
        loadMosaic(page);
    }, 50);
}

function rebuildMosaicPageIndexes() {
    $(".page-index").remove();
    for (var i = 0; i < _mosaic_pages + 1; i++) {
        var li = $("<li class='page-item page-index' />").toggleClass("active", i == 0);
        var btn = $("<a class='page-link' />").text(i + 1).attr("data-page", i);

        li.append(btn).insertBefore($(".page-next"));
    }

    $("#bin-paging").show();
}

function enableMosaicPaginationButtons() {
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
    $("#mosaic").css("cursor","wait");

    var binDataUrl = "/api/" + _dataset + "/bin/" + _bin +
        "?view_size=" + viewSize +
        "&scale_factor=" + scaleFactor;

    $.get(binDataUrl, function(data){

        // Update the coordinates for the image
        _coordinates = JSON.parse(data["coordinates"]);

        // Indicate to the user that the mosaic is clickable
        $("#mosaic").css("cursor","pointer");

        // Re-enable next/previous buttons
        enableMosaicPaginationButtons();

        // Update the paging
        if (data["num_pages"] != _mosaic_pages) {
            _mosaic_pages = data["num_pages"];

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

    $.get(mosaicUrl, function(data){
        $("#mosaic").attr("src", "data:image/png;base64," + data);
        $("#mosaic-loading").hide();
        $("#mosaic").show();
    });
}

function changeMosaicPage(pageNumber) {
    _mosaic_page = pageNumber;

    delayedMosaic(pageNumber);
    updateMosaicPaging();
}

function updateMosaicPaging() {
    $(".page-previous").toggleClass("disabled", (_mosaic_page <= 0));
    $(".page-next").toggleClass("disabled", (_mosaic_page >= _mosaic_pages));

    $.each($(".page-index a"), function() {
        var isSelected = $(this).data("page") == _mosaic_page;

        $(this).closest("li").toggleClass("active", isSelected);
    });

    $("#bin-paging").show();
}


//************* Map Methods ***********************/


//************* Plotting Methods  ***********************/
function initPlotData() {
    $.get("/api/plot/" + _bin, function(data){
        _plotData = data;

        var plotXAxis = $("#plot-x-axis");
        var plotYAxis = $("#plot-y-axis");

        $.each(data, function(key) {
            plotXAxis.append($("<option />").text(key));
            plotYAxis.append($("<option />").text(key));
        });

        plotXAxis.val(PLOT_X_DEFAULT);
        plotYAxis.val(PLOT_Y_DEFAULT);

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
    $("#share-button").click(function (e) {
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
        $("#bin-header").css("pointer-events","none");
    });

    // Changing the view size of the mosaic
    $("#view-size").change(function () {
        var viewSize = $("#view-size").val();
        var vs = viewSize.split("x");
        var height = parseInt(vs[1]);

        $('#mosaic-loading').height(height);

        changeBin(currentBinId, true);
    });

    // Changing the scale factor for the mosaic
    $("#scale-factor").change(function(e){
        changeBin(currentBinId, true);
    });

    // Bin navigation (next/prev)
    $("#previous-bin, #next-bin").click(function(e){
        e.preventDefault();

        changeBin($(this).data("bin"), true);
    });

    // Mosaic paging
    $("#bin-paging")
        .on("click", ".page-previous", function(e){
            e.preventDefault();

            if (_mosaic_page > 0)
                changeMosaicPage(_mosaic_page - 1);
        })
        .on("click", ".page-next", function(e){
            e.preventDefault();

            if (_mosaic_page < _mosaic_pages)
                changeMosaicPage(_mosaic_page + 1);
        })
        .on("click", ".page-index a", function(e){
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
}

//************* Initialization methods and page hooks ***********************/
$(function(){

    // Misc UI elements based on constants
    $("#max-images").text(MAX_SELECTABLE_IMAGES);

    initEvents();

    initPlotData();
});
