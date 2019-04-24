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