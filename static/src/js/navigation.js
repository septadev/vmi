/**
 * Created by AXLL on 8/19/2014.
 */



$(document).ready(function(){
  /* append session_id and pid to every hyperlink*/
  var sessionid = sessionStorage.getItem("session_id");
  var companyid = sessionStorage.getItem("company_id");
  console.log("session id = ",sessionid);
      $('a').each(function()
      {
          var href = $(this).attr('href');
          href += (href.match(/\?/) ? '&' : '?') + 'session_id=' + sessionid + '&pid=' + companyid;
          $(this).attr('href', href);
      });
  /* show company name*/
  var companyname = sessionStorage.getItem("company_name");
  console.log("company name: ",companyname);
  $('#vendor').html("Hi, " + companyname);

    $("#logout").click(function(){
            console.log("logging out");
            $.ajax({
                type: "POST",
                url: "/vmi/session/destroy",
                contentType: "application/json; charset=utf-8",
                data: '{"jsonrpc":"2.0","method":"call","params":{"session_id": null, "context": {}},"id":"r0"}',
                success: function(data){
                    alert("You've logged out");
                    window.location.href = 'index';
                }
            })
        });
});