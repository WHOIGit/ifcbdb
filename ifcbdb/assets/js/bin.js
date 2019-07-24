//************* Local Variables ***********************/
var _bin = "";                  // Bin Id
var _dataset = "";              // Dataset Name
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
    for (var i = 0; i < numBinPages + 1; i++) {
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
        if (data["num_pages"] != numBinPages) {
            numBinPages = data["num_pages"];

            rebuildMosaicPageIndexes();
        }

        updatePaging();

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
    currentBinPage = pageNumber;

    delayedMosaic(pageNumber);
    updatePaging();
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
}

//************* Initialization methods and page hooks ***********************/
$(function(){

    // Misc UI elements based on constants
    $("#max-images").text(MAX_SELECTABLE_IMAGES);

    initEvents();

    initPlotData();
});
