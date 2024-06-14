//************* Local Variables ***********************/
var _bin = ""; // Bin Id
var _dataset = ""; // Dataset Name (for filtering)
var _locations_dataset = ""; // Dataset name use for filtering w/o it being set to the primary dataset in bin mode
var _tags = ""; // Tags, comma separated (for filtering)
var _instrument = ""; // Instrument name (for filtering)
var _cruise = ""; // Cruise ID (for filtering)
var _sampleType = ""; // Sample Type (for filtering)
var _mosaicPage = 0; // Current page being displayed in the mosaic
var _mosaicPages = -1; // Total number of pages for the mosaic
var _coordinates = []; // Coordinates of images within the current mosaic
var _isMosaicLoading = false; // Whether the mosaic is in the process of loading
var _isBinLoading = false; // Whether the bin is in the process of loading
var _plotData = null; // Local storage of the current bin's plot data
var _map = null; // Current Leaflet map
var _marker = null; // Current marker shown on the map
var _binIcon = null; // Icon used for marking bins on the map
var _selectedIcon = null; // Icon used for the currently selected bin on the map
var _datasetIcon = null; // Icon used for marking datasets on the map
var _markers = null; // Used for marker clustering on the map
var _markerList = []; // Used for marker clustering on the map
var _fixedMarkers = null; // Used for marker clustering on the map
var _selectedMarkers = null; // Used for the currently selected bin (will only ever have one item)
var _selectedMarker = null; // The marker used to show the currently selected bin

var _workspace = "mosaic"; // The current workspace a user is seeing
var _pendingMapLocations = null; // The next map positions to render (see notes in updateMapLocations)
var _csrf = null; // CSRF token from Django for post requests
var _userId = null; // Id of the currently logged in user
var _userStaff = null; // is user.is_staff True?
var _commentTable = null; // Variable to keep track of the DataTables object once created
var _route = ""; // Tracks the route used to render this page (timeline or bin)
var _binTimestamp = null; // Timestamp for the currently selected bin
var _preventTimelineRelayout = false; // Used to prevent a relayout on the timeline when switching metrics
var _filterPopover; // Tracks the container created by the popover library for applying filters
var _originalMapHeight = null; // Initial size of the map on first render

//************* Common Methods ***********************/

// Generates a relative link to the current bin/dataset
function createLink() {
    // Bin Mode
    if (_route != "timeline")
        return createBinModeLink();

    // Timeline Mode
    return "/timeline?" +
        buildFilterOptionsQueryString(true) +
        (_bin != "" ? "&bin=" + _bin : "");
}

function createListLink(start, end) {
    if (!isFilteringUsed())
        return "javascript:;;";

    return "/list?" + getGroupingParameters(_bin) +
        "&start_date=" + start +
        "&end_date=" + end;
}

function createBinModeLink(bin) {
    if (bin == "" || typeof bin == "undefined") {
        bin = _bin;
    }

    return "/bin?" + getGroupingParameters(bin);
}

function getGroupingParameters(bin) {
    var parameters = buildFilterOptionsArray(true);
    if (bin != "")
        parameters.push("bin=" + bin);

    return parameters.length == 0 ? "" : parameters.join("&");
}

function getGroupingPayload(bin) {
    var payload = {};

    if (bin != "")
        payload["bin"] = bin;
    if (_locations_dataset != "")
        payload["dataset"] = _locations_dataset;
    if (_instrument != "")
        payload["instrument"] = _instrument;
    if (_tags != "") {
        payload["tags"] = _tags;
    }
    if (_cruise != "") {
        payload["cruise"] = _cruise;
    }
    if (_sampleType != "") {
        payload["sample_type"] = _sampleType;
    }

    return payload;
}

function createBinLink(bin) {
    if (_route == "bin") {
        return createBinModeLink(bin);
    }

    return "/timeline?" + getGroupingParameters(bin);
}

function createImageLink(imageId) {
    if (_route == "bin") {
        return "/image?image=" + imageId + "&bin=" + _bin;
    }

    var url = "/image?image=" + imageId;
    var parameters = getGroupingParameters(_bin);

    return url + (parameters != "" ? "&" + parameters : "");
}

// Switches between workspaces: map, plot, mosaic
function showWorkspace(workspace) {
    _workspace = workspace;

    $("#image-tab-content").toggleClass("d-none", !(workspace == "mosaic"));
    $("#plot-tab-content").toggleClass("d-none", !(workspace == "plot"));

    // After showing the map, Leaflet needs to have invalidateSize called to recalculate the
    //   dimensions of the map container (it cannot determine it when the container is hidden
    if (workspace == "map") {
        if (_map) {
            setTimeout(function() { _map.invalidateSize() }, 100);
        }

        if (_pendingMapLocations != null) {
            updateMapLocations(_pendingMapLocations);
            setTimeout(function(){ recenterMap(); }, 500);
        }
    }
}

//************* Bin Methods ***********************/
function updateBinStats(data) {
    var timestamp_iso = data["timestamp_iso"];
    var timestamp = moment.utc(timestamp_iso);

    var date_string = timestamp.format("YYYY-MM-DD");
    var time_string = timestamp.format("HH:mm:ss z");
    var initial_relative_time = timestamp.fromNow();

    $("#stat-date-time").html(
        date_string + "<br/>" +
        time_string + "<br/>" +
        "(<span data-livestamp='"+timestamp_iso+"'>"+initial_relative_time+"</span>)"
    );

    function showField(id, text) {
        $("#show-"+id).removeClass("d-none").addClass("d-flex");
        $("#stat-"+id).html(text);
    }
    function hideField(id) {
        $("#show-"+id).addClass("d-none").removeClass("d-flex");
        $("#stat-"+id).html("");
    }
    function showOrHideField(data, id) {
        if (data[id]) {
            showField(id, data[id]);
        } else {
            hideField(id);
        }
    }

    $("#stat-instrument").html(data["instrument"]);
    $("#stat-instrument-link").attr('href','/timeline?instrument='+data["instrument"]+'&bin='+_bin);
    $("#stat-num-triggers").html(data["num_triggers"]);
    $("#stat-num-images").html(data["num_images"]);
    $("#stat-trigger-freq").html(data["trigger_freq"]);
    $("#stat-ml-analyzed").html(data["ml_analyzed"]);
    $("#stat-concentration").html(data["concentration"]);
    $("#stat-cruise").html(data["cruise"]);
    $("#stat-sample-type").html(data["sample_type"]);
    $("#stat-size").html(filesize.filesize(data["size"]));
    $("#stat-skip")
        .text(data["skip"] ? "Yes" : "No")
        .data("skipped", data["skip"]);
    if(data["lat"] > -9999 && data["lng"] > -9999) {
        showField("lat", data["lat_rounded"]);
        showField("lon", data["lng_rounded"]);
    } else {
        hideField("lat");
        hideField("lon");
    }
    showOrHideField(data, "depth");
    showOrHideField(data, "cruise");
    showOrHideField(data, "sample_type");
    showOrHideField(data, "cast");
    showOrHideField(data, "niskin");
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
            .attr("href", "/timeline?bin=" + _bin + "&dataset=" + data.datasets[i])
            .text(data.datasets[i])
        )
    }
}

function updateBinTags(data) {
    displayTags(data.tags);
    toggleTagInput(false);
}

function updateBinComments(data) {
    displayComments(data.comments);
}

function updateBinDownloadLinks(data) {
    var infix = '/data/';
    if(_dataset) {
        infix = '/' + _dataset + '/';
    } else if (data.primary_dataset) {
        infix = '/' + data.primary_dataset + '/';
    }
    $("#download-adc").attr("href", infix + _bin + ".adc");
    $("#download-hdr").attr("href", infix + _bin + ".hdr");
    $("#download-roi").attr("href", infix + _bin + ".roi");
    $("#download-zip").attr("href", infix + _bin + ".zip");
    $("#download-blobs").attr("href", infix + _bin + "_blob.zip");
    $("#download-features").attr("href", infix + _bin + "_features.csv");
    $("#download-class-scores").attr("href", infix + _bin + "_class_scores.csv");

    $.get('/api/has_products/' + _bin, function(r) {
        $("#download-blobs").toggle(r["has_blobs"]);
        $("#download-blobs-disabled").toggle(!r["has_blobs"]);

        $("#download-features").toggle(r["has_features"]);
        $("#download-features-disabled").toggle(!r["has_features"]);

        $("#download-class-scores").toggle(r["has_class_scores"]);
        $("#download-class-scores-disabled").toggle(!r["has_class_scores"]);

        // Update outline/blob links
        $("#detailed-image-blob-link").toggleClass("disabled", !r["has_blobs"]);
        $("#detailed-image-outline-link").toggleClass("disabled", !r["has_blobs"]);
    });
}

function changeToClosestBin(targetDate) {
    if (_isBinLoading || _isMosaicLoading)
        return false;

    _isBinLoading = true;
    _isMosaicLoading = true;

    var payload = {
        "csrfmiddlewaretoken": _csrf,
        "target_date": targetDate,
        "dataset": _dataset,
        "instrument": _instrument,
        "tags": _tags,
        "cruise": _cruise,
        "sample_type": _sampleType
    }

    $.post("/api/closest_bin", payload, function(resp) {
        if (resp.bin_id != "")
            changeBin(resp.bin_id, true);
    });
}

function changeToNearestBin(lat, lng) {
    if (_isBinLoading || _isMosaicLoading)
        return false;

    _isBinLoading = true;
    _isMosaicLoading = true;

    var payload = {
        csrfmiddlewaretoken: _csrf,
        dataset: _dataset,
        latitude: lat,
        longitude: lng,
        instrument: _instrument,
        tags: _tags,
        cruise: _cruise,
        sample_type: _sampleType
    };

    $.post("/api/nearest_bin", payload, function(resp) {
        if (resp.bin_id != "")
            changeBin(resp.bin_id, true);
    });
}

//************* Tagging Methods ***********************/
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

function displayTags(tags) {
    var list = $("#tags");
    list.empty();

    for (var i = 0; i < tags.length; i++) {
        var tag = tags[i];
        var li = $("<span class='badge badge-pill badge-light mx-1'>");
        var link = "timeline?tags=" + tag + "&" +
            buildFilterOptionsQueryString(false, _dataset, _instrument, null, _cruise, _sampleType);

        var span = li.html("<a href='"+link+"'>"+tag+"</a>");
        var icon = $("<i class='fas fa-times pl-1'></i>");
        var remove = $("<a href='javascript:;' class='remove-tag' data-tag='" + tag + "' />");

        li.append(span);

        if (_userId != null) {
            li.append(remove);
            remove.append(icon);
        }

        list.append(li);
    }
}

//************* Comment Methods ***********************/
function addComment() {
    var content = $("#comment-input").val().trim();
    if (content === "") {
        return;
    }

    var payload = {
        "csrfmiddlewaretoken": _csrf,
        "comment": content
    };

    $.post("/secure/api/add-comment/" + _bin, payload, function(data){
        $("#comment-input").val("");
        displayComments(data.comments);
    });
}

function editComment(id) {
    $.get("/secure/api/edit-comment/" + _bin + "?id=" + id, function(data){
        if (data.id && data.id > 0) {
            $("#comment-id").val(data.id);
            $("#comment-input").val(data.content);
            $("#cancel-comment").toggleClass("d-none", false);
            $("#update-comment").toggleClass("d-none", false);
            $("#confirm-comment").toggleClass("d-none", true);
        }
    })
}

function cancelComment() {
    $("#comment-id").val("");
    $("#comment-input").val("");
    $("#cancel-comment").toggleClass("d-none", true);
    $("#update-comment").toggleClass("d-none", true);
    $("#confirm-comment").toggleClass("d-none", false);
}

function updateComment() {
    var content = $("#comment-input").val().trim();
    var id = $("#comment-id").val();
    if (content === "" || id === "") {
        return;
    }

    var payload = {
        "csrfmiddlewaretoken": _csrf,
        "id": id,
        "content": content
    };

    $.post("/secure/api/update-comment/" + _bin, payload, function(data){
        $("#comment-input").val("");
        cancelComment();
        displayComments(data.comments);
    });
}

function deleteComment(id) {
    if (id == null || id == "")
        return;

    if (!confirm("Are you sure you want to delete this comment?"))
        return;

    var payload = {
        "csrfmiddlewaretoken": _csrf,
        "id": id
    };

    $.post("/secure/api/delete-comment/" + _bin, payload, function(data){
        displayComments(data.comments);
    });
}

function displayComments(comments) {
    $(".comment-total").text(comments.length);
    if (_commentTable != null) {
        _commentTable.clear();
        _commentTable.rows.add(comments);
        _commentTable.draw();
        return;
    }
    _commentTable = $("#binCommentsTable").DataTable({
        searching: false,
        lengthChange: false,
        data: comments,
        order: [[ 1, "desc" ]],
        columns: [
            { // Date
                render: function(data, type, row) {
                    return moment.utc(data).format("YYYY-MM-DD HH:mm:ss z");
                }
            },
            {}, // Comment
            {}, // User
            { // Edit/Delete
                targets: -1,
                render: function(data, type, row ) {
                    var html = "";
                    // Only show edit/delete if the user is staff
                    if (_userStaff) {
                        html +=
                            "<button class='btn btn-sm py-1 px-2 edit-comment' data-id='" + data + "'><i class='fas fa-edit'></i></button>" +
                            "<button class='btn btn-sm py-1 px-2 delete-comment' data-id='" + data + "'><i class='fas fa-minus-circle'></i></button>";
                    }

                    return html;
                }
            },
            { // User ID
                visible: false
            }
        ]
    });
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

    var binDataUrl = "/api/bin/" + _bin +
        "?view_size=" + viewSize +
        "&scale_factor=" + scaleFactor +
        "&include_coordinates=true" +
        "&" + buildFilterOptionsQueryString(true);

    $.post(binDataUrl, { "csrfmiddlewaretoken": _csrf }, function(data) {

        // Update the coordinates for the image
        _coordinates = JSON.parse(data["coordinates"]);

        // Indicate to the user that the mosaic is clickable
        $("#mosaic").css("cursor", "pointer");

        // Re-enable next/previous buttons

        if (data.previous_bin_id)
            $("#previous-bin").data("bin", data.previous_bin_id);
        if (data.next_bin_id)
            $("#next-bin").data("bin", data.next_bin_id);
	
        enableNextPreviousBinButtons();

        // Update the paging
        if (data["num_pages"] != _mosaicPages) {
            _mosaicPages = data["num_pages"];

            rebuildMosaicPageIndexes();
        }

        updateMosaicPaging();

        _isMosaicLoading = false;
    });

    var mosaicUrl = "/api/mosaic/encoded_image/" + _bin +
        "?view_size=" + viewSize +
        "&scale_factor=" + scaleFactor +
        "&page=" + pageNumber;

    $.get(mosaicUrl, function(data) {
        $("#mosaic").attr("src", "data:image/png;base64," + data);
        $("#mosaic-loading").hide();
        $("#mosaic").show();
    }).fail(function(data) {
        $("#mosaic-failed").show();
        $("#mosaic-loading").hide();
        _isMosaicLoading = false;
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

function findImageByPID(pid) {
    pid = pid.replace(/^0+/, "");
    
    for (var i = 0; i < _coordinates.length; i++) {
        if (_coordinates[i].pid.toString() == pid) {
            return _coordinates[i];
        }
    }

    return null;
}

//************* Map Methods ***********************/
function changeBinFromMap(pid) {
    changeBin(pid, true);
    showWorkspace("mosaic");

    $(".nav-link").toggleClass("active", false);
    $("#show-mosaic").toggleClass("active", true);
}


function resizeMap()
{
    if (_originalMapHeight == null) {
        _originalMapHeight = $("#map-container").height();
    }

    var mosaicSize = $("#mosaic-column-container").width();
    var containerSize = $("#mosaicPlotMapTabContent").width();
    var spaceLeft = containerSize - mosaicSize;

    // Account for some additional padding on the image
    var imageSize = $("#detailed-image").width() * 1.25;

    if (spaceLeft < imageSize) {
        $("#mosaic-top").prepend($("#mosaic-details"));
        $("#mosaic-details").toggleClass("order-2", false).toggleClass("order-1", true);
    } else {
        $("#mosaic-side").prepend($("#mosaic-details"));
        $("#mosaic-details").toggleClass("order-2", true).toggleClass("order-1", false);
    }

    var showingMosaicImage = !$("#mosaic-details").hasClass("d-none");
    var showingPlotImage = !$("#plotImages").hasClass("d-none");

    var height = _originalMapHeight;

    if (showingMosaicImage || showingPlotImage) {

        if (showingMosaicImage)
            height -= $("#mosaic-details").height();

        if (showingPlotImage)
            height -= $("#plotImages").height();

        if (height < _originalMapHeight / 2) {
            height = _originalMapHeight / 2
        }
    }

    $("#map-container").height(height);
    if (_map != null) {
        _map.invalidateSize();
    }
}

function changeMarker(index) {
    // If there was a selected marker, put it back in the clustering list
    if (_selectedMarker) {
        _selectedMarker.setIcon(_binIcon)
        _markerList.push(_selectedMarker);
        _markers.addLayers(_selectedMarker)
        _selectedMarkers.clearLayers();
    }

    // If there is no target marker, nothing more needs to be done
    if (index == null) {
        return;
    }

    // Remove the now selected layer from the main list (cluster)
    _markers.removeLayer(_markerList[index]);
    _markerList.splice(index, 1);

    // A secondary call to get the location of the select bin is required, because the currently stored lat/lng
    //   isn't always accurate. It will be the location of the marker, which is based on the spidering, and we
    //   need the actual location of that bin to plot it correctly. If we use the stored value, the marker will be
    //   put at the edge of the spidering effect
    $.get("/api/bin_location?pid=" + _bin, function(resp){
         if (resp.lat && resp.lng) {
            // Create a new marker based on the information on the matched marker from the main list
            let newMarker = L.marker(
                L.latLng(resp.lat, resp.lng),
                {
                    title: _bin,
                    icon: _selectedIcon
                }
            )

            if (_route == "timeline") {
                newMarker.bindPopup("Bin: <a href='javascript:changeBinFromMap(\"" + _bin + "\")'>" + _bin + "</a>");
            } else {
                let url = createBinModeLink(_bin);
                newMarker.bindPopup("Bin: <a href='" + url + "'>" + _bin + "</a>");
            }

            // Add the new marker to the map as it's own layer
            _selectedMarker = newMarker;
            _selectedMarkers.clearLayers();
            _selectedMarkers.addLayer(_selectedMarker);
         }

         selectMapMarker(_selectedMarker);
    });
}

function recenterMap() {
    if (_map == null)
        return;

    // If the current bin si already selected, nothing more needs to be done
    if (_selectedMarker != null && _selectedMarker.options.title == _bin)
        return;

    for (let i = 0; i < _markerList.length; i++) {
        let title = _markerList[i].options.title;

        if (title == _bin || (_dataset && title.includes(_dataset))) {
            changeMarker(i);
            return;
        }
    }

    if (_markerList.length == 0 && _selectedMarker != null) {
        _selectedMarker.options.title = _bin;

        if (_route == "timeline") {
            _selectedMarker._popup.setContent("Bin: <a href='javascript:changeBinFromMap(\"" + _bin + "\")'>" + _bin + "</a>");
        } else {
            let url = createBinModeLink(_bin);
            _selectedMarker._popup.setContent("Bin: <a href='" + url + "'>" + _bin + "</a>");
        }

        return;
    }

    // If this code is reached, it means that no location was found for the selected bin. Close all
    //   open popups and show the user a warning message
    changeMarker(null);
    _map.closePopup()
    _selectedMarker = null;
    $("#no-bin-location").toggleClass("d-none", false);
}

function selectMapMarker(marker) {
    // TODO: Make sure zooming to layer is no longer required (might have only been needed to handle clustering)
    // _selectedMarkers.zoomToShowLayer(marker, function(){
    //     marker.openPopup();
    // });
    marker.openPopup();

    let zoom = _map.getZoom();
    _map.setView(marker.getLatLng(), zoom);
    $("#no-bin-location").toggleClass("d-none", true);
}

function updateMapLocations(data) {
    if (!_map) {

        var lat = defaultLat;
        var lng = defaultLng;
        var bins = $.grep(data.locations, function(val) {
            return val[0] == _bin
        });

        if (bins.length > 0) {
            lat = bins[0][1];
            lng = bins[0][2];
        } else if (data.locations.length > 0) {
            lat = data.locations[0][1];
            lng = data.locations[0][2];
        }

        _map = createMap(lat, lng);

        // TODO: Re-enable clicking functionality, or is that not need since users click on hte map should change to that bin?
        // TODO:   ^ if so, what happens when clicking on a dataset?
        //_map.on("click", function(e) {
        //    changeToNearestBin(e.latlng.lat, e.latlng.lng);
        //});

        _binIcon = buildLeafletIcon("orange");
        _datasetIcon = buildLeafletIcon("red");
        _selectedIcon = buildLeafletIcon("violet");

        _markers = L.markerClusterGroup({
            chunkedLoading: true,
            chunkProgress: function updateMapStatus(processed, total, elapsed, layersArray) {},
            maxClusterRadius: 5,
            zoomToBoundsOnClick: false,
            iconCreateFunction: function(cluster) {
                var children = cluster.getChildCount();

                return new L.DivIcon({
                    html: '<div style="width:20px;height:20px;margin-left:0px; margin-top:0px"><span style="font-size:10px;line-height:22px"></span></div>',
                    className: 'text-center marker-cluster marker-cluster-custom',
                    iconSize: new L.Point(8, 8)
                });
            }

        });

        // This event is needed to make the disabling of zoomToBoundsOnClick work properly. Without it, if clicking
        //   on the cluster would have normally spiderfied the cluster, it won't. This forces the spiderfy to happen
        //   regarldess, making things work as a user would expect
        _markers.on('clusterclick', function (cluster) {
            cluster.layer.spiderfy();
        });

        _fixedMarkers = L.layerGroup();
        _selectedMarkers = L.layerGroup();
    }

    var locationData = data;
    _markers.clearLayers();
    _fixedMarkers.clearLayers();
    _selectedMarkers.clearLayers();
    _markerList = [];

    _selectedMarker = null;
    for (var i = 0; i < locationData.locations.length; i++) {
        var location = locationData.locations[i];
        var isBin = location[3] == "b";
        var title = location[0];
        var marker = L.marker(
            L.latLng(location[1], location[2]),
            {
                title: title,
                icon: isBin ? _binIcon : _datasetIcon
            }
        );

        if (isBin) {
            if (_route == "timeline") {
                marker.bindPopup("Bin: <a href='javascript:changeBinFromMap(\"" + title + "\")'>" + title + "</a>");
            } else {
                var url = createBinModeLink(title);
                marker.bindPopup("Bin: <a href='" + url + "'>" + title + "</a>");
            }

            // Keep the selected bin out of the clustering
            if (_bin == title) {
                marker.setIcon(_selectedIcon);
                _selectedMarker = marker;
            } else {
                _markerList.push(marker);
            }

        } else {
            var values = title.split("|");
            marker.bindPopup("Dataset: " + values[1]);
            _fixedMarkers.addLayer(marker);
            _markerList.push(marker);
        }
    }

    if (_markerList.length > 0) {
        _markers.addLayers(_markerList);
        _map.addLayer(_markers);
    }

    if (_selectedMarker != null) {
        _selectedMarkers.addLayer(_selectedMarker);

        // A slight delay is needed or the popup will not open. However, this indirectly as a nice "progressive"
        //   effect as the page is loading various components
        setTimeout(function() {
            _selectedMarker.openPopup();
        }, 500);

        $("#no-bin-location").toggleClass("d-none", true);
    }

    _map.addLayer(_fixedMarkers);
    _map.addLayer(_selectedMarkers);

    recenterMap();
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
        $("#share-modal .modal-title").text($("#share-modal .modal-title").data("default-text"));
        $("#share-link").val(base + createLink()).select();
    });

    // Copy the share link to the clipboard
    $("#copy-share-link").click(function(e) {
        e.preventDefault();

        $("#share-link").select();
        document.execCommand("Copy");
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

        var np = $(this).data("bin");

        if (_route == "bin") {
            window.location.href = createBinModeLink(np);
        } else {
            changeBin(np, true);
        }
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

    // Direct preview of an image by pid
    $("#preview-image").click(function(){
        $("#image-not-found").toggleClass("d-none", true);
        $("#mosaic-details").toggleClass("d-none", true);
        var img = findImageByPID($("#roi-number").val());
        if (img) {
            previewImage(img);
            return;
        }
        $("#mosaic-details").toggleClass("d-none", false);
        $("#image-not-found").toggleClass("d-none", false);
        $("#scale-bar").toggleClass("d-none", true);
        $(".detailed-image-link").toggleClass("d-none", true);
        resizeMap();
    });

    // Direct link of an image by pid
    $("#goto-image").click(function(){
        $("#image-not-found").toggleClass("d-none", true);
        $("#mosaic-details").toggleClass("d-none", true);
        var img = findImageByPID($("#roi-number").val());
        if (img) {
            var url = createImageLink(padDigits(img.pid, 5));
            location.href = url;
            return;
        }
        $("#mosaic-details").toggleClass("d-none", false);
        $("#image-not-found").toggleClass("d-none", false);
        $("#scale-bar").toggleClass("d-none", true);
        $(".detailed-image-link").toggleClass("d-none", true);
        resizeMap();
    });

    // Changing the metric shown on the timeline
    $("#ts-tabs .nav-link").click(function() {
        var metric = $(this).data("metric");

        timelineValid = false;
        timelineWaiting = false;
        _preventTimelineRelayout = true;
        createTimeSeries(metric, null, null);
    });

    // Showing the plot workspace
    $("#show-plot").click(function(e) {
        $("#mosaic-details").toggleClass("d-none", true);
        showWorkspace("plot");
    });

    // Showing the mosaic workspace
    $("#show-mosaic").click(function(e) {
        $("#plotImages").toggleClass("d-none", true);
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

        $("#binCommentsTable_wrapper").css("width","100%")
    });

    $("#cancel-comment").click(function(e){
        cancelComment();
    });

    $("#update-comment").click(function(e){
        updateComment();
    });

    $("#confirm-comment").click(function(e){
        addComment();
    });

    $("#binCommentsTable").on("click", ".delete-comment", function(e){
        deleteComment($(this).data("id"));
    });

    $("#binCommentsTable").on("click", ".edit-comment", function(e){
        editComment($(this).data("id"));
    });

    $("#stat-skip").click(function(e){
        if (_userId == null)
            return;

        var skipped = $(this).data("skipped");
        if (!skipped && !confirm("Are you sure you want to mark this bin as skipped?"))
            return;

        var payload = {
            "csrfmiddlewaretoken": _csrf,
            "bin_id": _bin,
            "skipped": skipped
        }

        $.post("/secure/api/toggle-skip", payload, function(resp) {
            $("#stat-skip")
                .text(resp["skipped"] ? "Yes" : "No")
                .data("skipped", resp["skipped"]);
        });
    });
}

//************* Initialization methods and page hooks ***********************/
$(function() {

    // Misc UI elements based on constants
    $("#max-images").text(MAX_SELECTABLE_IMAGES);

    initEvents();
    //initPlotData();
    initBinFilter("timeline");
});
