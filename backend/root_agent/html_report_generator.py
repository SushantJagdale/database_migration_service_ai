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

def get_aws_account_id():
    """Fetches the AWS Account ID."""
    try:
        client = boto3.client("sts")
        return client.get_caller_identity()["Account"]
    except Exception as e:
        print(f"Error fetching AWS Account ID: {e}")
        return "Unknown"

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

        data = {"metadata": {}, "checks": {}}
        lines = section_content.split('\n')
        section = None
        in_checks_table = False
        current_check = None

        # The first line is the agent name, which we can skip or use as a title
        # For example: "MySQL\n\n## RDS Instance Metadata..."
        
        for line in lines:
            if line.startswith("## RDS Instance Metadata"):
                section = "metadata"
                in_checks_table = False
            elif line.startswith("## Prerequisite Checks"):
                section = "checks"
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

def generate_html_table(data, columns):
    """Generates a single HTML table with rowspan for metadata and multi-color statuses."""
    if not data or not data.get("checks"):
        return ""

    num_checks = len(data["checks"])
    if num_checks == 0:
        return "<p>No prerequisite checks were performed for this instance.</p>"

    column_display_names = {
        "DBInstanceIdentifier": "Database Name",
        "Engine": "DB Engine",
        "EngineVersion": "Engine Version",
        "Region": "Region",
        "check_name": "Param Check",
        "status": "Status",
        "configure_dms_job": "Configure DMS Job",
        "start_dms_job": "Start DMS Job",
        "check_dms_status": "Check DMS Status",
        "promote_database": "Promote Database"
    }

    html = "<table><tr>"
    for col in columns:
        display_name = column_display_names.get(col, col.replace('_', ' ').title())
        html += f"<th>{display_name}</th>"
    html += "</tr>"

    metadata = data.get("metadata", {})
    db_id = metadata.get("DBInstanceIdentifier", "").replace("-", "") # Sanitize for ID
    is_first_row = True

    for check_name, status in data["checks"].items():
        html += "<tr>"

        if is_first_row:
            for col in columns:
                if col not in ["check_name", "status", "configure_dms_job", "start_dms_job", "check_dms_status", "promote_database"]:
                    value = metadata.get(col, "N/A")
                    html += f"<td rowspan={num_checks}>{value}</td>"
        
        status_lines = status.split('<br>')
        formatted_status_lines = []
        for line in status_lines:
            status_text = line.upper()
            if "PASS" in status_text:
                status_class = "pass"
            elif "FAIL" in status_text:
                status_class = "fail"
            else:
                status_class = "info"
            formatted_status_lines.append(f"<span class='{status_class}'>{line}</span>")
        
        formatted_status = "<br>".join(formatted_status_lines)
        
        html += f"<td><strong>{check_name}</strong></td>"
        html += f"<td class='status-cell'>{formatted_status}</td>"

        if is_first_row:
            html += f"<td rowspan={num_checks}><button id='configure-btn-{db_id}' onclick='handleButtonClick(this, \"DMS Job Configured!\", \"start-btn-{db_id}\")'>Configure DMS Job</button></td>"
            html += f"<td rowspan={num_checks}><button id='start-btn-{db_id}' onclick='handleButtonClick(this, \"Database Replication has Started!\", \"check-btn-{db_id}\")' disabled>Start DMS Job</button></td>"
            html += f"<td rowspan={num_checks}><button id='check-btn-{db_id}' onclick='handleButtonClick(this, \"Database is in CDC status!, lag is 0\", \"promote-btn-{db_id}\")' disabled>Check DMS Status</button></td>"
            html += f"<td rowspan={num_checks}><button id='promote-btn-{db_id}' onclick='handleButtonClick(this, \"Database is Promoted..!\", null)' disabled>Promote Database</button></td>"

        html += "</tr>"
        is_first_row = False
    
    html += "</table>"
    return html

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
        body { font-family: sans-serif; margin: 2em; background-color: #f9f9f9; }
        h1, h2 { color: #333; }
        table { border-collapse: collapse; width: 100%; margin-bottom: 2em; box-shadow: 0 2px 3px rgba(0,0,0,0.1); }
        th, td { border: 1px solid #ddd; padding: 12px; text-align: left; }
        th { background-color: #607D8B; color: white; }
        tr:nth-child(even) { background-color: #f2f2f2; }
        .pass, .fail, .info { display: inline-flex; align-items: center; gap: 8px; }
        .pass { color: green; }
        .fail { color: red; }
        .info { color: #00529B; }
        .status-cell .pass, .status-cell .fail, .status-cell .info { font-weight: bold; }
        .status-cell .pass::before, .status-cell .fail::before, .status-cell .info::before { content: ''; display: inline-block; width: 12px; height: 12px; border-radius: 50%; }
        .status-cell .pass::before { background-color: green; }
        .status-cell .fail::before { background-color: red; }
        .status-cell .info::before { background-color: #00529B; }
        .container { max-width: 1200px; margin: auto; background: white; padding: 2em; border-radius: 8px; }
        button { background-color: #3498db; color: white; padding: 10px 15px; border: none; border-radius: 4px; cursor: pointer; }
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
    
    aws_account_id = get_aws_account_id()
    
    mysql_reports = parse_md_report("mysql_report.md")
    postgres_reports = parse_md_report("postgres_report.md")
    
    columns = ["DBInstanceIdentifier", "Engine", "EngineVersion", "Region", "check_name", "status", "configure_dms_job", "start_dms_job", "check_dms_status", "promote_database"]
    
    mysql_html = ""
    if mysql_reports:
        mysql_html = "<h2>MySQL Instances Report</h2>" + generate_html_tables(mysql_reports, columns)
        
    postgres_html = ""
    if postgres_reports:
        postgres_html = "<h2>PostgreSQL Instances Report</h2>" + generate_html_tables(postgres_reports, columns)
    
    template = html_template.replace("{{AWS_ACCOUNT_ID}}", aws_account_id)
    report_container = mysql_html + postgres_html
    template = html_template.replace("<!-- The consolidated report will be inserted here -->", report_container)
    
    os.makedirs("artifacts", exist_ok=True)
    with open("artifacts/final_report.html", "w") as f:
        f.write(template)
        
    print("Generated final_report.html")

if __name__ == '__main__':
    main()
