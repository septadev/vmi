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
});