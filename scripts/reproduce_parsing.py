import asyncio
import sys

sys.path.insert(0, ".")

from app.llm.ollama import OllamaClient

TEXT = """RIT Alumni Resume – Software Engineering/Computer Science
RICHARD TIGER
GitHub account
www.linkedin.com/in/name
Senior Software 
Engineer
(585) XXX-XXXX (Cellular)
Name@gmail.com
Career Summary:
Dedicated Senior Software Engineer with over twenty-five years’ experience in all phases of computer 
software design and development in high technology environments. Experienced in both Embedded 
System Level Software and Applications Level Software. Led software development teams that consistently 
provide software products that meet, or exceed, overall customer expectations.
Computer Skills:
Computer Languages: C++, C, XML, Intel Assembler, Motorola Assembler, PLM/86, Java, 
COBOL, FORTRAN, Basic
Operating Systems: MS Windows Vista, XP, 2000, NT, 9x, Mac OS X, Solaris, HP/UX, 
MS/PC DOS, MTOS, VAX/VMS, UNIX, QNX, Linux, CCI PERPOS
Packages/Methodologies/
Tools:
Visual Studio .NET, Adobe Acrobat SDK, Orbix (CORBA), MS 
FrontPage, Windows Multi-Threaded applications, Rational Rose 
Clear Case, Visual Source Safe, InstallShield, Parallels, MS Project
Windows: .NET Framework, MFC, COM, Win32, Twain/ISIS Scanner Drivers
Hardware: IBM PC, Apple Intel Mac, Sun Ultra Workstation, HP Workstation, 
DEC VAX, CCI-632FT
Instruction: Developed and taught a C# programming language course for GE 
Consulting Services and Greece Central School District Continuing 
Education Department
Experience:
COMPANY NAME, Rochester, New York 2007 - 2010
Senior Software Engineering Consultant 
Currently assigned to Client Company, Rochester NY, Product Support
Responsible for the design, and implementation, of major enhancements and fixes to the 
AutoVue Innova Blood Analysis system. Analyzed customer data to determine problem cause in 
order to determine corrective actions required. Provided technical support to Product Testing and 
Quality Assurance Group. This Object Oriented C++ System was developed in Microsoft Visual 
Studio 6.0. Key accomplishments included deliverables three months ahead of schedule, and 
improved collaboration between marketing and engineering departments.
COMPANY NAME, Rochester, New York 1997 - 2007
Senior Software Engineer 
Created functional requirements and design & test specifications associated with the development of 
specific software subsystems of high speed, high volume, digital printers, and a 65 PPM Production 
Scanner. Designed, coded and tested major enhancements and fixes to software components. Analyzed
customer data to determine problem cause in order to determine corrective actions required. Key 
accomplishments included 35% increase in productivity, and marked process improvement of analyzer 
system.
- Project Lead (2003 – 2007) – Managed the Imposition Viewer/Content Edit module of the Digital Front 
End for the NexPress 2100 family Color Printer. Planned, scheduled and implemented enhancements 
and maintenance requests for the subsystem. This product was developed in Microsoft Visual Studio 
2003 C++ utilizing Adobe’s Acrobat SDK and CORBA to facilitate communications. Project resulted in 
$1million in cost savings to client.
- Sr. Software Engineer (2005 – 2007) – Designed and implemented major enhancements and fixes to 
the Job Ticketing Subsystem of the SmartBoard Image Processing system. This Object Oriented C++ 
System was developed in Microsoft Visual Studio .NET 2003 and also utilizes Adobe’s Acrobat SDK. Enhancements resulted in more streamlined process for entire system. 
RIT Alumni Resume – Software Engineering/Computer Science
Name Page 2
(585) XXX-XXXX
Experience: (Cont.)
COMPANY NAME (Cont.)
- Project Lead (1997 – 2003) - Implemented all Front End Software Group scanner related interface 
software products. Developed an Adobe "Plug-In" module that allows a user to scan a document from 
any Twain compliant scanning device and send the captured PDF document to Kodak’s High Speed 
printer. Participated in all phases of the development cycle of a COM based Virtual Scanner 
Driver (VSD), allowing higher-level clients (i.e. COM clients, not end users) consistent, and easy, 
access to multiple types of production scanners. Assumed responsibility for the maintenance and 
enhancement responsibilities for a COM/CORBA bridge specifically tailored to the COM objects 
developed for the VSD. Orbix by Iona was the Orb software used. Communication to the scanners 
was implemented via a SCSI interface using the ASPI for Windows toolkit by Adaptec. Managed group 
of twelve programmers and technical writers.
COMPANY NAME, Rochester, New York 1990 - 1997
Senior Software Engineer
Performed assignments that required the application of engineering principles, techniques, and procedures 
in an ISO-9001 Organization. Duties included the creation of functional requirements and design & test 
specifications associated with the introduction and maintenance of a complex proprietary Process Control 
System. Designed, coded and tested major enhancements and fixes to software components. Analyzed 
customer data to determine problem causes in order to determine corrective actions required. Provided 
technical support to Quality Assurance Group, Engineering Services Group, Marketing/Training 
Departments and, when required, the customer directly. 
- Technical Project Lead for the development, implementation and testing of the embedded ABB MOD 
300 Ethernet drivers and control firmware of the Intel 552 based, Ethernet Interface Board, following 
IEEE 802.3 & Ethernet Type II standards. Managed group of ten programmers.
- Project Lead for the development, maintenance and enhancement of several ABB MOD 300 Based 
communications interfaces. These interfaces facilitated the transfer of data between the MOD 300 and 
External/Host computers via either Serial or Ethernet connections. Supervised three software 
engineers.
- Maintained and enhanced, the ABB MOD 300 Template Generator Product. This PC based product, 
written in C and dBase, allowed customers to create/maintain MOD 300 process databases off-line on 
their personal computer for later download to the MOD 300.
- Designed and implemented low level translation functions that provided the transitional bridge between 
the ABB Master System and the MOD 300 system.
COMPANY NAME, Rochester, New York 1983 - 1990
Senior Software Engineering Consultant/Site Supervisor 
Summary of Clients:
• Eastman Kodak Company, Rochester NY, Copy Products Division: 1989 - 1990
• Computer Consoles, Inc,. Rochester NY, Core Products Group: 1986 - 1989
• Eastman Kodak Co., KAD, TechNet Quality Management System Group: 1984 - 1986
• Computer Consoles, Inc. Engineering Interfaces Group: November 1983 to 1984
Professional Associations:
ACM, Rochester NY Chapter, 1997 – Present – Treasurer, 2009 - Present
IEEE, Rochester NY Chapter, 2002 – Present 
Education: ROCHESTER INSTITUTE OF TECHNOLOGY Rochester NY
BS Dual Major: Computer Science and Business Administration, Marketing"""

async def test_parse():
    client = OllamaClient()
    # Test with truncation
    truncated_text = TEXT[:4000]
    print(f"--- Truncated Text Length: {len(truncated_text)} ---")
    try:
        result = await client.extract(truncated_text)
        print("\n--- Result (Truncated) ---")
        print(result.model_dump_json(indent=2))
    except Exception as e:
        print(f"\n--- Error (Truncated) ---: {e}")

    # Test without truncation
    print(f"\n--- Full Text Length: {len(TEXT)} ---")
    try:
        result = await client.extract(TEXT)
        print("\n--- Result (Full) ---")
        print(result.model_dump_json(indent=2))
    except Exception as e:
        print(f"\n--- Error (Full) ---: {e}")

if __name__ == "__main__":
    asyncio.run(test_parse())
