import pytest
from backend.application.use_cases.scraping.academic_calendar.scrape.parse import parse_course_offerings

def test_parse_course_offerings_sk690():
    # 1. The Mock HTML
    # (Try running this first. If it passes, replace this string with the actual
    # HTML from the WLU page source to see exactly why the real page is failing!)
    html_content = """
    <html lang="en"><head>
	<meta http-equiv="Content-Type" content="text/html; charset=ISO-8859-1">
	<title>Wilfrid Laurier University - Graduate Calendar - 2025/2026 - Faculty of Human and Social Sciences - Criminology</title>
	<style>undefined</style><link rel="StyleSheet" href="css/style_wlu.css?ts=20200602_01" type="text/css" media="screen,print">
	<link rel="StyleSheet" href="css/style_wlu_print.css?ts=20200602_01" type="text/css" media="print">
	<link rel="StyleSheet" href="css/style_cal.css?ts=20200602_01" type="text/css" media="screen">
	<meta http-equiv="X-UA-Compatible" content="IE=edge">

	<!--[if IE 6]><link rel="stylesheet" href="css/style_wlu_ie6.css" type="text/css" media="screen" /><![endif]-->
	<!--[if lte IE 9]><link rel="stylesheet" href="css/style_wlu_ie.css" type="text/css" media="screen" /><![endif]-->

	<script type="text/javascript">
		<!--
		function findPos(obj) {
			// gets the 'top' and 'left' positions of the object.

			var curtop = 0;
			var curleft = 0;
			if (obj.offsetParent) {
				while (obj.offsetParent) {
					curtop += obj.offsetTop;
					curleft += obj.offsetLeft;
					obj = obj.offsetParent;
				}
			} else {
				if (obj.y) curtop += obj.y;
				if (obj.x) curleft += obj.x;
			}
			var r = Array();
			r[0] = curtop;
			r[1] = curleft;
			return r;
		}

		function showGlossaryDef(obj, def) {
			// will move a special "glossary DIV" to appropriate spot and put term information into it.

			gPos = findPos(obj);
			if ((gPos[0] > 0) && (gPos[1] > 0)) {
				gDiv = document.getElementById("glossaryDef");
				if (gDiv) {
					gDiv.innerHTML = def.replace(/#QUOTE#/g, '"');
					gDiv.style.top = (gPos[0] + 15) + "px";
					gDiv.style.left = gPos[1] + "px";
					gDiv.style.visibility = "visible";
					gDiv.style.display = "inline";
				}
			}
		}

		function hideGlossaryDef() {
			gDiv = document.getElementById("glossaryDef");
			if (gDiv) {
				gDiv.style.visibility = "hidden";
				gDiv.style.display = "none";
			}
		}

		function hideSelect() {
			var DL_bIE = document.all ? true : false; // initialize var to identify IE
			if (DL_bIE) { // if browser is IE, then...
				var numforms = document.forms.length;
				for (f = 1; f < numforms; f++) {
					var numformelements = document.forms[f].elements.length;
					for (counter = 0; counter < numformelements; counter++) {
						var thisselect = document.forms[f].elements[counter];
						thisselect.style.visibility = "hidden";
					}
				}
			}
		}

		function showSelect() {
			var numforms = document.forms.length;
			for (f = 1; f < numforms; f++) {
				var numformelements = document.forms[f].elements.length;
				for (counter = 0; counter < numformelements; counter++) {
					var thisselect = document.forms[f].elements[counter];
					thisselect.style.visibility = "visible";
				}
			}
		}


		startList = function() {
			if (document.all && document.getElementById) {
				navRoot = document.getElementById("nav");
				for (i = 0; i < navRoot.childNodes.length; i++) {
					node = navRoot.childNodes[i];
					if (node.nodeName == "LI") {
						node.onmouseover = function() {
							this.className += " over";
						}
						node.onmouseout = function() {
							this.className = this.className.replace(" over", "");
						}
					}
				}
			}
		}
		window.onload = startList;
		//
		-->
	</script>
<link rel="preconnect" href="https://fonts.googleapis.com" crossorigin="use-credentials"><link rel="preconnect" href="https://fonts.gstatic.com"><link rel="stylesheet" href="https://fonts.googleapis.com/css2?family=Mulish:wght@200;300;400;500;600;700;800;900&amp;display=swa"></head>

<body>

	<div class="header clearfix" role="banner">

		<a class="skip-to-content-link" href="#main">Skip to content</a>
		<a class="top-link" name="top"></a>

		<div class="header-logo">
			<a href="http://www.wlu.ca/">
				<img src="images/layout/laurier_logo.gif" alt="Wilfrid Laurier University">
			</a>
		</div>

		
		<div class="header-decoration">
			<img class="book-image" src="images/layout/book_white.gif" alt="Book decoration" role="presentation" aria-hidden="true">
			<a href="index.php?cal=3&amp;y=91">
				<img src="./images/cms/corner/91/grad-calendar-2025-2026.gif" width="268" height="101" alt="Graduate Calendar - 2025/2026">
			</a>
		</div>

		<div class="header-tagline">
			<img src="images/layout/canadian-excellence.gif" width="267" height="18" alt="Canadian Excellence">
		</div>
	</div>

	
	<div class="wrapper">

		<div id="deptnav" class="sidebar" role="navigation" aria-label="Left side navigation">

			<h2><a href="index_old.php?cal=3&amp;y=91">Graduate Calendar 2025/2026</a></h2>
<ul>
	<li><a href="section.php?cal=3&amp;s=1135&amp;y=91">The University</a></li>
	<li><a href="section.php?cal=3&amp;s=1136&amp;y=91">University Graduate Regulations</a></li>
	<li><a href="section.php?cal=3&amp;s=1137&amp;y=91">University Policies</a></li>
	<li><a href="section.php?cal=3&amp;s=1138&amp;y=91">Faculty of Arts</a></li>
	<li><a href="section.php?cal=3&amp;s=1147&amp;y=91">Faculty of Education</a></li>
	<li class="current"><a href="section.php?cal=3&amp;s=1149&amp;y=91">Faculty of Human and Social Sciences</a></li>
	<li><a href="section.php?cal=3&amp;s=1148&amp;y=91">Faculty of Liberal Arts</a></li>
	<li><a href="section.php?cal=3&amp;s=1140&amp;y=91">Faculty of Music</a></li>
	<li><a href="section.php?cal=3&amp;s=1134&amp;y=91">Faculty of Science</a></li>
	<li><a href="section.php?cal=3&amp;s=1139&amp;y=91">Lazaridis School of Business and Economics</a></li>
	<li><a href="section.php?cal=3&amp;s=1141&amp;y=91">Lyle S. Hallman Faculty of Social Work</a></li>
	<li><a href="section.php?cal=3&amp;s=1146&amp;y=91">School of International Policy and Governance</a></li>
	<li><a href="section.php?cal=3&amp;s=1142&amp;y=91">Martin Luther University College</a></li>
	<li><a href="section.php?cal=3&amp;s=1143&amp;y=91">Fees and Financial Support</a></li>
	<li><a href="section.php?cal=3&amp;s=1144&amp;y=91">Fellowships and Scholarships</a></li>
	<li><a href="section.php?cal=3&amp;s=1145&amp;y=91">Academic Medals</a></li>
</ul>
<hr>
<ul>
	<li><a href="index_old.php?cal=3&amp;y=91">Search this Calendar</a></li>
	<li><a href="glossary.php?cal=3&amp;y=91">Glossary</a></li>
</ul>
			<div id="deptcontact">
	<h1>Contact Us:</h1>
		<strong>Dr. Carrie Sanders, Graduate Co-ordinator</strong><br>			email: <a href="mailto:csanders@wlu.ca">csanders@wlu.ca</a><br>
				</div>

		</div>

		<div id="main" class="main" role="main">

			<a name="mcontent"></a>

			<div class="breadcrumb">
<img src="images/layout/redlistarrow.gif" alt="List bullet" role="presentation" aria-hidden="true"> <a href="section.php?cal=3&amp;s=1149&amp;y=91">Faculty of Human and Social Sciences</a>&nbsp;<img src="images/layout/redlistsmbullet.gif" alt="list bullet" role="presentation" aria-hidden="true"> <a href="department.php?cal=3&amp;d=3065&amp;s=1149&amp;y=91">Criminology</a>&nbsp;</div>

			<div class="content">
<h1>Criminology</h1>
<p>

   
  <b>Graduate Program Co-ordinator: <a title="" target="" href="mailto:csanders@wlu.ca">Carrie Sanders</a>, PhD</b> 
</p><div class="reqs">
<div class="greyheading">Department Information on this page</div>
<ul class="proginfo">
<li><a href="#Programs">Programs</a></li>
<li><a href="#Course_Offerings">Course Offerings</a></li>
</ul>
<div class="clear">&nbsp;</div>
</div>
<a name="Programs"></a>
<div class="reqs">
<div class="heading">Program Information</div>
<p style="padding-top:0px;"></p><ul>
<li><a href="program.php?cal=3&amp;d=3065&amp;p=6945&amp;s=1149&amp;y=91">Master of Arts in Criminology</a></li>
</ul><p></p>
<div class="clear">&nbsp;</div>
<div class="returntotop"><a href="#top">Top</a></div>
</div>
<a name="Course_Offerings"></a>
<div class="reqs">
<table>
<caption>Course Offerings</caption>
<tbody><tr><th>Course #</th><th>Title</th><th>Credits</th></tr>
<tr class="zebra">
   <td><a href="course.php?c=74924&amp;cal=3&amp;d=3065&amp;s=1149&amp;y=91">CC601</a></td>
	<td>Qualitative Fieldwork into the Study of Deviance</td>
	<td>0.5</td>
</tr>
<tr>
   <td><a href="course.php?c=74925&amp;cal=3&amp;d=3065&amp;s=1149&amp;y=91">CC602</a></td>
	<td>Advanced Quantitative Research Methods</td>
	<td>0.5</td>
</tr>
<tr class="zebra">
   <td><a href="course.php?c=74926&amp;cal=3&amp;d=3065&amp;s=1149&amp;y=91">CC603</a></td>
	<td>Theories of Crime and Crime Control</td>
	<td>0.5</td>
</tr>
<tr>
   <td><a href="course.php?c=74927&amp;cal=3&amp;d=3065&amp;s=1149&amp;y=91">CC604</a></td>
	<td>The Critical Turn in Criminology</td>
	<td>0.5</td>
</tr>
<tr class="zebra">
   <td><a href="course.php?c=74928&amp;cal=3&amp;d=3065&amp;s=1149&amp;y=91">CC606</a></td>
	<td>Research and Professionalization Seminar</td>
	<td>0.5</td>
</tr>
<tr>
   <td><a href="course.php?c=74929&amp;cal=3&amp;d=3065&amp;s=1149&amp;y=91">CC607</a></td>
	<td>The Charter and Criminal Justice</td>
	<td>0.5</td>
</tr>
<tr class="zebra">
   <td><a href="course.php?c=74930&amp;cal=3&amp;d=3065&amp;s=1149&amp;y=91">CC608</a></td>
	<td>Crime, Politics, and Political Deviance in Global Perspective</td>
	<td>0.5</td>
</tr>
<tr>
   <td><a href="course.php?c=74931&amp;cal=3&amp;d=3065&amp;s=1149&amp;y=91">CC609</a></td>
	<td>Crimes of Globalization</td>
	<td>0.5</td>
</tr>
<tr class="zebra">
   <td><a href="course.php?c=74932&amp;cal=3&amp;d=3065&amp;s=1149&amp;y=91">CC610</a></td>
	<td>Transnational Crime</td>
	<td>0.5</td>
</tr>
<tr>
   <td><a href="course.php?c=74933&amp;cal=3&amp;d=3065&amp;s=1149&amp;y=91">CC611</a></td>
	<td>International Human Rights in Criminal Justice</td>
	<td>0.5</td>
</tr>
<tr class="zebra">
   <td><a href="course.php?c=74934&amp;cal=3&amp;d=3065&amp;s=1149&amp;y=91">CC612</a></td>
	<td>The Contemporary Caribbean: Crime and Human Security</td>
	<td>0.5</td>
</tr>
<tr>
   <td><a href="course.php?c=74935&amp;cal=3&amp;d=3065&amp;s=1149&amp;y=91">CC613</a></td>
	<td>Global Proliferation of Terrorism</td>
	<td>0.5</td>
</tr>
<tr class="zebra">
   <td><a href="course.php?c=74943&amp;cal=3&amp;d=3065&amp;s=1149&amp;y=91">CC614</a></td>
	<td>Advanced Studies on Policing</td>
	<td>0.5</td>
</tr>
<tr>
   <td><a href="course.php?c=74939&amp;cal=3&amp;d=3065&amp;s=1149&amp;y=91">CC615</a></td>
	<td>Comparative Youth Justice Systems</td>
	<td>0.5</td>
</tr>
<tr class="zebra">
   <td><a href="course.php?c=74940&amp;cal=3&amp;d=3065&amp;s=1149&amp;y=91">CC616</a></td>
	<td>Sociology of Law</td>
	<td>0.5</td>
</tr>
<tr>
   <td><a href="course.php?c=74941&amp;cal=3&amp;d=3065&amp;s=1149&amp;y=91">CC617</a></td>
	<td>Penology</td>
	<td>0.5</td>
</tr>
<tr class="zebra">
   <td><a href="course.php?c=74942&amp;cal=3&amp;d=3065&amp;s=1149&amp;y=91">CC618</a></td>
	<td>Deviance and Diversity</td>
	<td>0.5</td>
</tr>
<tr>
   <td><a href="course.php?c=74936&amp;cal=3&amp;d=3065&amp;s=1149&amp;y=91">CC621</a></td>
	<td>Cultural Criminology</td>
	<td>0.5</td>
</tr>
<tr class="zebra">
   <td><a href="course.php?c=74937&amp;cal=3&amp;d=3065&amp;s=1149&amp;y=91">CC623</a></td>
	<td>Contemporary Issues in Crime and Media</td>
	<td>0.5</td>
</tr>
<tr>
   <td><a href="course.php?c=74938&amp;cal=3&amp;d=3065&amp;s=1149&amp;y=91">CC625</a></td>
	<td>Special Topics in Criminology</td>
	<td>0.5</td>
</tr>
<tr class="zebra">
   <td><a href="course.php?c=74944&amp;cal=3&amp;d=3065&amp;s=1149&amp;y=91">CC650</a></td>
	<td>Directed Study</td>
	<td>0.5</td>
</tr>
<tr>
   <td><a href="course.php?c=74945&amp;cal=3&amp;d=3065&amp;s=1149&amp;y=91">CC699</a></td>
	<td>Thesis</td>
	<td>0.0</td>
</tr>
</tbody></table>
<div class="clear">&nbsp;</div>
<div class="returntotop"><a href="#top">Top</a></div>
</div>
			</div> <!-- /.content -->

		</div> <!-- /.main -->

		
<div id="contentRHS" class="sidebar" role="navigation" aria-label="Right side navigation">
	<img src="./images/layout/picture_right.gif" alt="Decorative image" role="presentation">

		<div class="calright">
	<h4>Academic &amp; Related Dates 2025/2026</h4>
	<ul class="dates">
	<li><a href="dates.php?cal=3&amp;y=91">All Dates</a></li>
	</ul>

			<hr class="calrightrule">
	<h4>Other Calendars</h4>
	<ul class="archivedcal">
		<li class="ruled"><a href="index_old.php?cal=3&amp;y=89">Graduate Calendar (2024/2025)</a></li>
		<li class="ruled"><a href="index_old.php?cal=3&amp;y=88">Graduate Calendar (2023/2024)</a></li>
		<li class="ruled"><a href="index_old.php?cal=3&amp;y=86">Graduate Calendar (2022/2023)</a></li>
		<li class="ruled"><a href="index_old.php?cal=3&amp;y=84">Graduate Calendar (2021/2022)</a></li>
		<li><a href="/index.php">more...</a></li>
		</ul>
		</div>
</div> <!-- /.sidebar -->

	</div> <!-- /.wrapper -->

	<div class="footer" role="contentinfo">

		<div class="footer-top">
			<div>
				<a href="https://www.wlu.ca/about/locations-maps-and-parking/contact-us.html">Contact WLU</a>
			</div>
			<div>
				<span>© 2026 Wilfrid Laurier University</span>
			</div>
			<div>
				<img src="images/layout/footer_red.gif" alt="Ontario, Canada" title="Ontario, Canada">
			</div>
		</div> <!-- /.footer-top -->

		<div class="footer-bottom">
			<div>
				<span>Wilfrid Laurier University | 75 University Avenue West, Waterloo, Ontario, Canada  N2L 3C5</span>
			</div>
			<div>
				<span>Phone: 519.884.1970 | Fax: 519.886.9351</span>
			</div>
			<div>
				<span class="brantford">&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;
			</span></div>
		</div> <!-- /.footer-bottom -->

	</div> <!-- /#footer -->

	



</body></html>
    
    
    
    """

    base_url = "https://academic-calendar.wlu.ca/department.php?cal=3&d=3065&s=1149&y=91"

    # 2. Run the function in isolation
    results = parse_course_offerings(html_content, base_url)

    # 3. Print the results to the console so you can see what it actually parsed
    print("\n--- EXTRACTED COURSES ---")
    for res in results:
        print(res)
    print("-------------------------\n")

    # 4. Assertions to ensure SK690 parsed perfectly
    assert len(results) == 2, f"Expected 2 courses, but found {len(results)}. Table targeting likely failed!"

    sk690_course = results[0]
    subject, number, title, url, credit_json = sk690_course

    assert subject == "SK"
    assert number == "690"
    assert title == "Social Work Practice"
    assert url == "https://academic-calendar.wlu.ca/course.php?c=12345&cal=3&y=91"
    assert credit_json == {"min": 0.5, "max": 0.5, "unit": "credits"}

if __name__ == "__main__":
    # Allows you to run this as a standard python script without needing pytest installed
    test_parse_course_offerings_sk690()
    print("Test passed successfully!")