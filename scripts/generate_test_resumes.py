"""Generate edge-case test resumes as PDFs."""
import os

from fpdf import FPDF

OUT = r"C:\Users\Arman\Downloads\test_resumes"
os.makedirs(OUT, exist_ok=True)


def pdf(filename: str, lines: list[str]) -> str:
    doc = FPDF(format="A4")
    doc.set_margins(20, 20, 20)
    doc.add_page()
    doc.set_auto_page_break(auto=True, margin=20)
    doc.set_font("Helvetica", size=10)
    for line in lines:
        doc.cell(0, 7, line if line.strip() else "", ln=True)
    path = os.path.join(OUT, filename)
    doc.output(path)
    return path


# 1. Fully filled senior developer
pdf("01_senior_dev.pdf", [
    "ARTHUR KOWALSKI",
    "arthur.kowalski@techcorp.com | +1 (555) 123-4567 | San Francisco, CA",
    "",
    "SUMMARY",
    "Senior software engineer with 12 years building scalable distributed systems at FAANG companies.",
    "",
    "EXPERIENCE",
    "Google - Staff Software Engineer (2018-2024)",
    "Meta - Senior Engineer (2015-2018)",
    "Startup Inc - Backend Engineer (2012-2015)",
    "",
    "SKILLS",
    "Python, Go, Kubernetes, Terraform, PostgreSQL, Redis, Kafka, gRPC, AWS, GCP",
    "",
    "EDUCATION",
    "MIT - Bachelor of Science, Computer Science (2012)",
    "",
    "CERTIFICATIONS",
    "AWS Solutions Architect Professional | CKA (Certified Kubernetes Administrator)",
])

# 2. Junior candidate - fresh graduate, minimal experience
pdf("02_junior_fresh.pdf", [
    "Sophie Martin",
    "sophiemartin@gmail.com | 07911 123456 | London, UK",
    "",
    "Recent graduate looking for first role in data analysis.",
    "",
    "Education",
    "University College London - BSc Statistics (2025)",
    "",
    "Skills",
    "Python, Excel, SQL (basic), Tableau",
    "",
    "Projects",
    "Final year dissertation: predicting housing prices using linear regression",
    "Internship: 3-month data entry at local council",
])

# 3. No email at all
pdf("03_no_email.pdf", [
    "Marcus Webb",
    "Phone: +44 7700 900123 | Bristol, UK",
    "",
    "Product Manager with 5 years experience in fintech.",
    "",
    "Experience",
    "Barclays - Product Manager (2020-2025)",
    "Monzo - Associate PM (2019-2020)",
    "",
    "Skills",
    "Product strategy, Agile, JIRA, SQL, A/B testing, stakeholder management",
    "",
    "Education",
    "University of Bristol - BA Economics (2019)",
])

# 4. No name - anonymous resume
pdf("04_no_name.pdf", [
    "contact@anonymous.dev | Remote",
    "",
    "Full-stack developer, 7 years experience.",
    "",
    "Skills: React, Node.js, TypeScript, Docker, PostgreSQL, AWS Lambda",
    "",
    "Companies: Freelance clients, Agency work",
    "",
    "Education: Self-taught + bootcamp (2017)",
])

# 5. Completely blank PDF
pdf("05_blank.pdf", [""])

# 6. Barely any text - one liner
pdf("06_minimal_text.pdf", ["John. Developer. john@dev.io"])

# 7. Special characters - Armenian / non-ASCII name
pdf("07_special_chars.pdf", [
    "Armen Hakobyan",
    "armen.hakobyan@airecruitment.com | +374 55 123456 | Yerevan, Armenia",
    "",
    "Senior Financial Analyst with 8 years in banking sector.",
    "",
    "Experience",
    "Acme Bank - Senior Analyst (2018-2025)",
    "HSBC Armenia - Analyst (2016-2018)",
    "",
    "Skills",
    "Financial modeling, Risk analysis, Bloomberg, Excel, SQL, Armenian banking regulations, Basel III",
    "",
    "Education",
    "Yerevan State University - MSc Finance (2016)",
    "American University of Armenia - BA Economics (2014)",
])

# 8. Duplicate email - same as Becky Business (should be rejected by API)
pdf("08_duplicate_email.pdf", [
    "Rebecca B. Clone",
    "beckyB@uofga.edu | (706) 999-9999 | Atlanta, GA",
    "",
    "Marketing specialist, 3 years experience.",
    "",
    "Skills: Social media, Google Analytics, HubSpot, Salesforce",
    "",
    "Education: Georgia Tech - BA Communications (2022)",
])

# 9. Extremely long resume - many skills and jobs
pdf("09_very_long.pdf", [
    "Dr. Victoria Steinberg",
    "v.steinberg@research.edu | +1 (617) 555-9900 | Boston, MA",
    "",
    "SUMMARY",
    "Principal Data Scientist with 18 years in academia and industry. PhD in Machine Learning.",
    "",
    "EXPERIENCE",
    "MIT Media Lab - Principal Researcher (2015-2025)",
    "Harvard Medical School - Data Science Lead (2010-2015)",
    "IBM Research - Research Scientist (2007-2010)",
    "Google Brain - Research Intern (2006)",
    "Microsoft Research - Research Intern (2005)",
    "",
    "SKILLS",
    "Python, R, Julia, MATLAB, TensorFlow, PyTorch, JAX, Scikit-learn, XGBoost,",
    "SQL, Spark, Hadoop, Hive, Kafka, Flink, Airflow, Kubernetes, Docker,",
    "AWS SageMaker, GCP Vertex AI, Azure ML, Statistics, Bayesian methods,",
    "NLP, Computer Vision, Reinforcement Learning, Graph Neural Networks,",
    "Clinical trials design, FDA regulatory submissions, HIPAA compliance",
    "",
    "EDUCATION",
    "MIT - PhD Machine Learning (2007)",
    "Stanford University - MSc Statistics (2004)",
    "UC Berkeley - BSc Mathematics (2002)",
    "",
    "PUBLICATIONS",
    "45 peer-reviewed papers, 3200+ citations",
    "Best Paper Award - NeurIPS 2019",
    "",
    "CERTIFICATIONS",
    "AWS ML Specialty | GCP Professional Data Engineer | PMP",
])

# 10. Non-standard format - no structure, just a paragraph
pdf("10_unstructured.pdf", [
    "Hi my name is Jake Thompson and I am looking for work. I used to work at a coffee shop "
    "and then I did some IT support for a small company called TechHelp Ltd for about 2 years. "
    "I know a bit of Python and I have used Windows and Mac computers. "
    "I went to school in Manchester and got my A-levels. "
    "My email is jake.thompson@outlook.com and my phone is 07834 567890. "
    "I am a hard worker and quick learner. I am based in Manchester, UK.",
])

print("Generated test resumes:")
for f in sorted(os.listdir(OUT)):
    size = os.path.getsize(os.path.join(OUT, f))
    print(f"  {f} ({size} bytes)")
