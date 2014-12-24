/**
 * Created by M. A. Ruberto on 1/30/14.
 */

$(document).ready(function() {
if(isAPIAvailable()) {
$('#files').bind('change', handleFileSelect);
}
});
function isAPIAvailable() {
// Check for the various File API support.
    if (window.File && window.FileReader && window.FileList && window.Blob) {
// Great success! All the File APIs are supported.
        return true;
    } else {
// source: File API availability - http://caniuse.com/#feat=fileapi
// source: <output> availability - http://html5doctor.com/the-output-element/
        document.writeln('The HTML5 APIs used in this form are only available in the following browsers:<br />');
// 6.0 File API & 13.0 <output>
        document.writeln(' - Google Chrome: 13.0 or later<br />');
// 3.6 File API & 6.0 <output>
        document.writeln(' - Mozilla Firefox: 6.0 or later<br />');
// 10.0 File API & 10.0 <output>
        document.writeln(' - Internet Explorer: Not supported (partial support expected in 10.0)<br />');
// ? File API & 5.1 <output>
        document.writeln(' - Safari: Not supported<br />');
// ? File API & 9.2 <output>
        document.writeln(' - Opera: Not supported');
        return false;
    }
}
function handleFileSelect(evt) {
    var files = evt.target.files; // FileList object
    var file = files[0];
// read the file metadata
    var output = ''
    output += '<span style="font-weight:bold;">' + escape(file.name) + '</span><br />\n';
    output += ' - FileType: ' + (file.type || 'n/a') + '<br />\n';
    output += ' - FileSize: ' + file.size + ' bytes<br />\n';
    output += ' - LastModified: ' + (file.lastModifiedDate ? file.lastModifiedDate.toLocaleDateString() : 'n/a') + '<br />\n';
    // append submit button for upload form
    output += ' <button class="oe_button oe_field_button" type="submit" id="OBEY"><span title="Start the upload of the selected file.">Upload File</span></button>'
// read the file contents
    printTable(file);
// post the results
    $('#list').append(output);
}
function printTable(file) {
    var reader = new FileReader();
    reader.readAsText(file);
    reader.onload = function (event) {
        var csv = event.target.result;
        var data = $.csv.toArrays(csv);
        // html for table header - this should be dynamic...
        var header = '<thead><tr><th rowspan="2">Month</th><th rowspan="2">Day</th><th rowspan="2">Year</th><th rowspan="2">Vendor P/N</th> ' +
            '<th rowspan="2">Bin</th><th rowspan="2">Description</th><th rowspan="2">UOM</th><th colspan="3">Quantity</th>' +
            '<th rowspan="2">SEPTA P/N</th><th rowspan="2">Line</th><th rowspan="2">PO</th><th rowspan="2">Supplier</th>' +
            '<th rowspan="2">Packing List</th><th rowspan="2">Destination</th><th rowspan="2">Ship Type</th></tr>' +
            '<tr><th>Ordered</th><th>Shipped</th><th>Backordered</th></tr></thead>\r\n';
        // html for table footer - this should be dynamic...
        var footer = '<tfoot><tr><th rowspan="2">Month</th><th rowspan="2">Day</th><th rowspan="2">Year</th><th rowspan="2">Vendor P/N</th> ' +
            '<th rowspan="2">Bin</th><th rowspan="2">Description</th><th rowspan="2">UOM</th><th>Ordered</th><th>Shipped</th><th>Backordered</th>' +
            '<th rowspan="2">SEPTA P/N</th><th rowspan="2">Line</th><th rowspan="2">PO</th><th rowspan="2">Supplier</th>' +
            '<th rowspan="2">Packing List</th><th rowspan="2">Destination</th><th rowspan="2">Ship Type</th></tr>' +
            '<tr><th colspan="3">Quantity</th> </tr></tfoot>\r\n';

        var html = header + footer + '<tbody>';
        // construct table from rows in csv file
        for (var row in data) {
            html += '<tr>\r\n';
            for (var item in data[row]) {
                html += '<td>' + data[row][item] + '</td>\r\n';
            }
            html += '</tr>\r\n';
        }
        html += '</tbody>\r\n';
        $('#contents').html(html);   // append table to DOM
        // intitialize and instantiate the datatable plugin
        $('#contents').dataTable({
            "sDom": 'T<"clear">lfrtip',
            "oTableTools": {
                "sSwfPath": "/vmi/static/src/js/datatables/extras/TableTools/media/swf/copy_csv_xls_pdf.swf"
            },
            "sPaginationType": "full_numbers"
        });

    };
    reader.onerror = function () {
        alert('Unable to read ' + file.fileName);
    };
}
