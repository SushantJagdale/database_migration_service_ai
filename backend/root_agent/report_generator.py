import boto3
import os

# --- Consolidated Report Generation Logic ---

def generate_report(agent_name, rds_metadata, validation_results, suggestions):
    """Generates a Markdown report of the findings."""
    report = f"# Pre-Migration Report for {agent_name}\n\n"

    report += "## RDS Instance Metadata\n"
    if rds_metadata:
        for key, value in rds_metadata.items():
            report += f"- **{key}:** {value}\n"
    else:
        report += "Could not retrieve RDS metadata.\n"

    report += "\n## Prerequisite Checks\n"
    report += "| Check | Status |\n"
    report += "|---|---|\n"
    for check, result in validation_results.items():
        result_single_line = result.replace('\n', '<br>')
        report += f"| {check} | {result_single_line} |\n"
        
    report += "\n## Suggested Alterations\n"
    if suggestions and "No alterations needed" not in suggestions:
        report += "```bash\n"
        report += suggestions
        report += "\n```\n"
    else:
        report += "No alterations needed.\n"

    return report

# --- HTML Generation and Parsing ---

def parse_md_report(file_path):
    """Parses a Markdown report file that may contain multiple reports, returning a list of data dictionaries."""
    if not os.path.exists(file_path):
        return []

    with open(file_path, 'r') as f:
        content = f.read()

    reports = []
    # Split the content by the main header of each report
    report_sections = content.split('# Pre-Migration Report for')
    
    for section_content in report_sections:
        if not section_content.strip():
            continue

        data = {"metadata": {}, "checks": {}, "suggestions": ""}
        lines = section_content.split('\n')
        section = None
        in_checks_table = False
        in_code_block = False
        current_check = None
        suggestion_lines = []

        for line in lines:
            if line.startswith("## RDS Instance Metadata"):
                section = "metadata"
                in_checks_table = False
            elif line.startswith("## Prerequisite Checks"):
                section = "checks"
                in_checks_table = False
            elif line.startswith("## Suggested Alterations"):
                section = "suggestions"
                in_checks_table = False
            elif section == "metadata" and line.startswith("- **"):
                parts = line.split(":** ", 1)
                if len(parts) == 2:
                    key = parts[0].replace("- **", "").replace("**", "")
                    value = parts[1]
                    data["metadata"][key] = value
            elif section == "checks" and "|---" in line:
                in_checks_table = True
            elif in_checks_table and line.startswith("|"):
                parts = [p.strip() for p in line.split("|") if p.strip()]
                if len(parts) == 2:
                    current_check = parts[0]
                    if current_check.upper() != "CHECK":
                        data["checks"][current_check] = parts[1]
                elif len(parts) == 1 and current_check:
                    # This handles multi-line statuses within the same check
                    data["checks"][current_check] += "<br>" + parts[0]
            elif section == "suggestions":
                if line.strip().startswith("```"):
                    in_code_block = not in_code_block
                elif in_code_block or (line.strip() and "No alterations needed" not in line):
                    suggestion_lines.append(line)

        if suggestion_lines:
            data["suggestions"] = "\n".join(suggestion_lines).strip()
        
        if data["metadata"] or data["checks"]:
            reports.append(data)
            
    return reports

def generate_html_tables(report_data_list, columns):
    """Generates HTML tables for a list of report data."""
    if not report_data_list:
        return ""

    html = ""
    for data in report_data_list:
        html += generate_html_table(data, columns)
    return html

def get_rds_specs(instance_class):
    """Returns (vCPUs, Memory) for a given AWS RDS instance class."""
    if not instance_class:
        return "N/A", "N/A"
        
    ic_lower = instance_class.lower()
    
    RDS_SPECS = {
        "db.t3.micro": (2, "1 GiB"),
        "db.t3.small": (2, "2 GiB"),
        "db.t3.medium": (2, "4 GiB"),
        "db.t3.large": (2, "8 GiB"),
        "db.t3.xlarge": (4, "16 GiB"),
        "db.t3.2xlarge": (8, "32 GiB"),
        
        "db.t2.micro": (1, "1 GiB"),
        "db.t2.small": (1, "2 GiB"),
        "db.t2.medium": (2, "4 GiB"),
        "db.t2.large": (2, "8 GiB"),
        
        "db.m5.large": (2, "8 GiB"),
        "db.m5.xlarge": (4, "16 GiB"),
        "db.m5.2xlarge": (8, "32 GiB"),
        "db.m5.4xlarge": (16, "64 GiB"),
        "db.m5.8xlarge": (32, "128 GiB"),
        
        "db.r5.large": (2, "16 GiB"),
        "db.r5.xlarge": (4, "32 GiB"),
        "db.r5.2xlarge": (8, "64 GiB"),
        "db.r5.4xlarge": (16, "128 GiB"),
    }
    
    if ic_lower in RDS_SPECS:
        return RDS_SPECS[ic_lower]
        
    parts = ic_lower.split('.')
    if len(parts) >= 3:
        size = parts[2]
        size_map = {
            "nano": (1, "0.5 GiB"),
            "micro": (2, "1 GiB"),
            "small": (2, "2 GiB"),
            "medium": (2, "4 GiB"),
            "large": (2, "8 GiB"),
            "xlarge": (4, "16 GiB"),
            "2xlarge": (8, "32 GiB"),
            "4xlarge": (16, "64 GiB"),
            "8xlarge": (32, "128 GiB"),
            "12xlarge": (48, "192 GiB"),
            "16xlarge": (64, "256 GiB"),
            "24xlarge": (96, "384 GiB"),
        }
        if size in size_map:
            return size_map[size]
            
    return "Unknown", "Unknown"

def generate_html_table(data, columns):
    """Generates a single HTML table with rowspan for metadata and multi-color statuses."""
    if not data or not data.get("checks"):
        return ""

    import html as html_lib
    num_checks = len(data["checks"])
    if num_checks == 0:
        return "<p>No prerequisite checks were performed for this instance.</p>"

    column_display_names = {
        "DBInstanceIdentifier": "Database Name",
        "Engine": "DB Engine",
        "EngineVersion": "Engine Version",
        "Region": "Region",
        "DBInstanceClass": "Instance Class",
        "vCPU": "vCPU",
        "Memory": "Memory",
        "Storage": "Storage Size",
        "check_name": "Param Check",
        "status": "Status"
    }

    html = "<table><tr>"
    for col in columns:
        display_name = column_display_names.get(col, col.replace('_', ' ').title())
        html += f"<th>{display_name}</th>"
    html += "</tr>"

    metadata = data.get("metadata", {})
    # Enrich metadata with RDS vCPU and Memory specs
    db_class = metadata.get("DBInstanceClass")
    vcpu, memory = get_rds_specs(db_class)
    metadata["vCPU"] = vcpu
    metadata["Memory"] = memory
    metadata["Storage"] = f"{metadata.get('AllocatedStorage', 'N/A')} GiB"

    db_id = metadata.get("DBInstanceIdentifier", "")
    is_first_row = True

    for check_name, status in data["checks"].items():
        html += "<tr>"

        if is_first_row:
            for col in columns:
                if col not in ["check_name", "status"]:
                    value = html_lib.escape(str(metadata.get(col, "N/A")))
                    html += f"<td rowspan={num_checks}>{value}</td>"
        
        status_lines = status.split('<br>')
        formatted_status_lines = []
        for line in status_lines:
            status_text = line.upper()
            if "PASS" in status_text:
                status_class = "pass"
            elif "FAIL" in status_text:
                status_class = "fail"
            elif "WARNING" in status_text:
                status_class = "warn"
            else:
                status_class = "info"
            formatted_status_lines.append(f"<span class='{status_class}'>{html_lib.escape(line)}</span>")
        
        formatted_status = "<br>".join(formatted_status_lines)
        
        html += f"<td><strong>{html_lib.escape(check_name)}</strong></td>"
        html += f"<td class='status-cell'>{formatted_status}</td>"

        html += "</tr>"
        is_first_row = False
    
    html += "</table>"

    suggestions = data.get("suggestions", "")
    if suggestions:
        escaped_suggestions = html_lib.escape(suggestions)
        escaped_db_id = html_lib.escape(str(db_id))
        html += (
            f"<details class='remediation-box'>"
            f"<summary>Suggested Remediation &amp; Prerequisite Commands for <code>{escaped_db_id}</code></summary>"
            f"<pre><code>{escaped_suggestions}</code></pre>"
            f"</details>"
        )

    return html

def find_report_file(filename):
    """Finds the report file directly in the backend directory."""
    backend_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    full_path = os.path.join(backend_dir, filename)
    return full_path

def main():
    """Generates the final HTML report."""
    
    html_template = """
<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>DMS Pre-requisites and Migration Report</title>
    <style>
        body { font-family: system-ui, -apple-system, sans-serif; background-color: #e5e7eb; }
        h1, h2 { color: #333; }
        table { border-collapse: collapse; width: 100%; margin-bottom: 0.75em; box-shadow: 0 4px 6px rgba(0,0,0,0.1); border-radius: 8px; overflow: hidden; }
        th, td { padding: 12px; text-align: left; }
        th { background-color: #607D8B; color: white; }
        tr:nth-child(even) { background-color: #f9f9f9; }
        .pass, .fail, .warn, .info { display: inline-flex; align-items: center; gap: 8px; }
        .pass { color: green; }
        .fail { color: red; }
        .warn { color: #b45309; }
        .info { color: #00529B; }
        .status-cell .pass, .status-cell .fail, .status-cell .warn, .status-cell .info { font-weight: bold; }
        .status-cell .pass::before, .status-cell .fail::before, .status-cell .warn::before, .status-cell .info::before { content: ''; display: inline-block; width: 12px; height: 12px; border-radius: 50%; flex-shrink: 0; }
        .status-cell .pass::before { background-color: green; }
        .status-cell .fail::before { background-color: red; }
        .status-cell .warn::before { background-color: #d97706; }
        .status-cell .info::before { background-color: #00529B; }
        .remediation-box { margin-bottom: 2em; background: #0f172a; color: #e2e8f0; border-radius: 8px; padding: 0.75em 1em; box-shadow: 0 2px 4px rgba(0,0,0,0.1); }
        .remediation-box summary { cursor: pointer; font-weight: 600; color: #38bdf8; outline: none; }
        .remediation-box pre { margin: 0.75em 0 0 0; overflow-x: auto; font-size: 0.85rem; line-height: 1.5; color: #f8fafc; }
        .container { max-width: 1200px; margin: auto; background: white; padding: 2em; border-radius: 8px; }
        button { background-color: #3498db; color: white; padding: 10px 20px; border: none; border-radius: 6px; cursor: pointer; }
        button:hover { background-color: #2980b9; }
        button:disabled { background-color: #cccccc; cursor: not-allowed; }
        .progress-bar-container { display: none; width: 100%; background-color: #f3f3f3; border-radius: 4px; margin-top: 10px; }
        .progress-bar { width: 0%; height: 20px; background-color: #4caf50; border-radius: 4px; text-align: center; line-height: 20px; color: white; }
    </style>
</head>
<body>
    <div class="container">
        <h1>DMS Pre-requisites and Migration Report</h1>
        <p><strong>AWS Account ID:</strong> {{AWS_ACCOUNT_ID}}</p>
        
        <!-- The consolidated report will be inserted here -->

    </div>
    <script>
        function handleButtonClick(button, message, nextButtonId) {
            button.disabled = true;
            const statusCell = button.parentElement;

            // Create and show progress bar
            const progressBarContainer = document.createElement('div');
            progressBarContainer.className = 'progress-bar-container';
            progressBarContainer.style.display = 'block';
            const progressBar = document.createElement('div');
            progressBar.className = 'progress-bar';
            progressBar.style.width = '0%';
            progressBar.innerText = '0%';
            progressBarContainer.appendChild(progressBar);
            statusCell.appendChild(progressBarContainer);

            // Animate progress bar
            let width = 0;
            const interval = setInterval(() => {
                if (width >= 100) {
                    clearInterval(interval);
                    // Show message
                    const messageSpan = document.createElement('span');
                    messageSpan.className = 'pass';
                    messageSpan.innerHTML = message;
                    statusCell.appendChild(messageSpan);
                    
                    // Enable next button
                    if (nextButtonId) {
                        const nextButton = document.getElementById(nextButtonId);
                        if (nextButton) {
                            nextButton.disabled = false;
                        }
                    }
                } else {
                    width++;
                    progressBar.style.width = width + '%';
                    progressBar.innerText = width + '%';
                }
            }, 30); // Adjust speed of progress bar here
        }
    </script>
</body>
</html>
"""
    
    aws_account_id = os.getenv("AWS_ACCOUNT_ID", "Not Provided")
    
    mysql_reports = parse_md_report(find_report_file("mysql_report.md"))
    postgres_reports = parse_md_report(find_report_file("postgres_report.md"))
    
    columns = ["DBInstanceIdentifier", "Engine", "EngineVersion", "Region", "DBInstanceClass", "vCPU", "Memory", "Storage", "check_name", "status"]
    
    mysql_html = ""
    if mysql_reports:
        mysql_html = "<h2>MySQL Instances Report</h2>" + generate_html_tables(mysql_reports, columns)
        
    postgres_html = ""
    if postgres_reports:
        postgres_html = "<h2>PostgreSQL Instances Report</h2>" + generate_html_tables(postgres_reports, columns)
    
    report_container = mysql_html + postgres_html
    template = html_template.replace("{{AWS_ACCOUNT_ID}}", aws_account_id).replace("<!-- The consolidated report will be inserted here -->", report_container)
    
    os.makedirs("artifacts", exist_ok=True)
    with open("artifacts/final_report.html", "w") as f:
        f.write(template)
        
    print("Generated final_report.html")

if __name__ == '__main__':
    main()