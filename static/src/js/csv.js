/**
 * Created by M. A. Ruberto on 1/30/14.
 */

$(document).ready(function() {
    sessionid = sessionStorage.getItem('session_id');
    company_id = sessionStorage.getItem(('company_id'));
    uid = sessionStorage.getItem(('user_id'));
    file_selected = false;
    if(isAPIAvailable()) {
        $('#files').bind('change', handleFileSelect);
        $('#files').bind('change', function(){
            if (file_selected){
                //$('#list').empty();
                //oTable.fnClearTable(0);
            }
            else{
                file_selected = true;
            }
            handleFileSelect;
        });
    }
    $(':file').change(function(){
        var file = this.files[0];
        var name = file.name;
        var size = file.size;
        var type = file.type;
        //Your validation
    });

    //$('form#upload_form').submit(function(){
    $('#list').on('click', '#OBEY', function(){
        //$('#upload_form').serialize();
        //var formData = new FormData($(this)[0]);
        if (str){
            $('.overlay').show();
            $.ajax({
                type: "POST",
                url: "/vmi/upload_file",
                contentType: "application/json; charset=utf-8",
                dataType: "json",
                data: '{"jsonrpc": "2.0", "method": "call", "params": {"session_id": "' + sessionid + '", "context": {}, "company_id": "' + company_id + '", "data": '+ str +'}, "id":"VMI"}',
                error: function (XMLHttpRequest, textStatus, errorThrown) {
                    console.log(XMLHttpRequest, textStatus, errorThrown);
                },
                success: function (data) {
                    if (data.result && data.result.code) { // script returned error
                        var output = '<div id="error" title="Upload Failed" style="color: #ff0000">';
                        output += 'Error code: ' + data.result.code + '<br />\n';
                        output += 'Error type: ' + data.result.data.type + '<br />\n';
                        output += 'Error detail: ' + data.result.data.text + '<br />\n';
                        output += '</div>';
                        // post the results
                        $('#list').append(output);
                        $('.overlay').hide();
                    }
                    else if (data.error) { // OpenERP error
                        var output = '<div id="error" title="Upload Failed" style="color: #ff0000">';
                        output += 'Server Error' + '<br />\n';
                        output += '</div>';
                        // post the results
                        $('#list').append(output);
                        $('.overlay').hide();
                    } // if
                    else { // successful transaction
                        //console.log('Success');
                        if ("code" in data.result){
                            alert(data.result["error"]);
                        }
                        else{
                            location.reload();
                        }
                    }

                }
            });
        }
    });

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
    var file_types = ['text/csv',
    'text/plain',
    'application/csv',
    'text/comma-separated-values',
    'application/excel',
    'application/vnd.ms-excel',
    'application/vnd.msexcel',
    'text/anytext',
    'application/octet-stream',
    'application/txt'];
    if ($.inArray(file.type, file_types) > -1) {
        // read the file metadata
        var output = '';
        output += ' - FileType: ' + (file.type || 'n/a') + '<br />\n';
        output += ' - FileSize: ' + file.size + ' bytes<br />\n';
        output += ' - LastModified: ' + (file.lastModifiedDate ? file.lastModifiedDate.toLocaleDateString() : 'n/a') + '<br />\n';
        // append submit button for upload form
        output += ' <button class="oe_button oe_field_button" id="OBEY"><span title="Start the upload of the selected file.">Upload File</span></button>';
        // read the file contents
        printTable(file);
        // post the results
        $('#list').empty();
        $('#list').append(output);
    }
    else{
        alert("Please upload a csv file");
    }



}
function printTable(file) {
    var reader = new FileReader();
    reader.readAsText(file);
    reader.onload = function (event) {
        var invalid_data = false;
        var csv = event.target.result;
        var csv_data = $.csv.toArrays(csv);
        var objArray = [];
        for (var i=1;i<csv_data.length;i++){
            objArray[i-1] = {};
            for (var j=0;j<csv_data[0].length;j++){
                var key = csv_data[0][j];
                objArray[i-1][key] = csv_data[i][j];
            }
        }
        var json = JSON.stringify(objArray);
        str = json.replace(/},/g, "},\r\n");
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
        for (var row = 1; row < csv_data.length; row++) {
            html += '<tr>\r\n';
            for (var item in csv_data[row]) {
                if ([0, 1, 2, 8, 10, 13, 14, 15].indexOf(parseInt(item)) > -1 && csv_data[row][item] == "") {
                    //var error_msg =  'Invalid data in row: ' + row+1 + ", item: " +  data[0][item];
                    html += '<td>' + csv_data[row][item] + '</td>\r\n';
                    alert('Invalid data in row: ' + row + ", item: " + csv_data[0][item]);
                    $("#OBEY").hide();
                }
                else {
                    html += '<td>' + csv_data[row][item] + '</td>\r\n';
                }
            }
            html += '</tr>\r\n';
        }
        html += '</tbody>\r\n';

        $('#contents').html(html);   // append table to DOM
        // intitialize and instantiate the datatable plugin
        if (oTable){
            fnClearTable(0);
        }
        else{
            var oTable = $('#contents').dataTable({
                //"bRetrieve": true,
                "bDestroy": true,
                "sPaginationType": "full_numbers"
            });
        }
    };
    reader.onerror = function () {
        alert('Unable to read ' + file.fileName);
    };
}
