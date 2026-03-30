# V BrevityBeta0.9.1. Building on BrevityBeta0.9 getting ready for Brevity1 release
# 0.9.1 bug fix to allow keyed code to decode if "A-Unknown" selected for station status. 
# 0.9.1 allow the enter key to trigger the brevity search
# 0.9.1 corrected 1 dropdown not reflecting file if brevity entered 
# 0.9.1 #out a section preventing the "Y" code from being used in menu 5.
# 0.9.1 #out a section preventing the "Y" code from being used in menu 5.
# 1.0 Converted from Tkinter to PyQt5 for qt5ct theming support on Linux


import sys
import re
import json
import traceback
import os
import glob
import logging
logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(levelname)s: %(message)s")
# Global variables
positions = {}
updating_menus = False
emergency_list_mapping = {}
current_file = None
gui_widgets = {}

def show_status_message(message, timeout=5000):
    try:
        if 'status_bar' in globals():
            status_bar = globals()['status_bar']
            status_bar.showMessage(message, timeout)
    except NameError:
        logging.debug(f"Cannot show status message '{message}'")
    except Exception as e:
        logging.debug(f"Error in show_status_message: {str(e)}")

def get_json_files():
    global emergency_list_mapping
    emergency_list_mapping = {}
    brevity_dir = os.path.dirname(os.path.abspath(__file__)) # Use script's directory
    logging.info(f"Scanning directory {brevity_dir} for JSON files")
    if not os.path.exists(brevity_dir):
        logging.error(f"Directory {brevity_dir} does not exist")
        return emergency_list_mapping
    files = sorted(glob.glob(os.path.join(brevity_dir, "[0-9]-*.json")))
    logging.info(f"Found files: {files}")
    if not files:
        logging.warning("No JSON files found matching pattern [0-9]-*.json")
        return emergency_list_mapping
    for file_path in files:
        filename = os.path.basename(file_path)
        logging.debug(f"Processing file: {filename}")
        if not re.match(r'^[0-9]-.*\.json$', filename, flags=re.IGNORECASE):
            logging.debug(f"Skipping {filename}: does not match pattern [0-9]-*.json")
            continue
        prefix = filename[0]
        try:
            with open(file_path, 'r', encoding='utf-8') as f:
                data = json.load(f)
            if validate_json_structure(data):
                if prefix in emergency_list_mapping:
                    logging.warning(f"Skipping duplicate emergency prefix {prefix} in {filename}")
                    continue
                emergency_list_mapping[prefix] = filename
                logging.info(f"Mapped emergency file {filename} to prefix {prefix}")
            else:
                logging.warning(f"Ignoring {filename} due to invalid JSON structure")
        except json.JSONDecodeError as e:
            logging.error(f"Invalid JSON in {filename}: {str(e)}")
        except PermissionError:
            logging.error(f"Permission denied accessing {filename}")
        except Exception as e:
            logging.error(f"Error processing {filename}: {str(e)}")
    logging.info(f"emergency_list_mapping = {emergency_list_mapping}")
    return emergency_list_mapping

def validate_json_structure(data):
    required_keys = ["emergency_type", "public_reaction", "station_response", "shared_impacts",
                     "emergency_group_order", "impact_group_order", "group_descriptions", "status_codes"]
    missing_keys = [key for key in required_keys if key not in data]
    if missing_keys:
        logging.warning(f"Missing required keys in JSON: {missing_keys}")
        return False
    if "A" not in data["emergency_type"]:
        logging.warning("Missing required code 'A' in emergency_type")
        return False
    if "A" not in data["status_codes"]:
        logging.warning("Missing required code 'A' in status_codes")
        return False
    return True

def generate_description(parts, severity_code, list_id, code, status_code, secondary_code, emergency_group, impact_group):
    station_group = "Unknown"
    for group_name, group in positions["station_response"].items():
        if isinstance(group, dict) and "items" in group and severity_code in group.get("items", []):
            station_group = group_name
            break
    public_group = "Unknown"
    for group_name, group in positions["public_reaction"].items():
        if isinstance(group, dict) and "items" in group and secondary_code in group.get("items", []):
            public_group = group_name
            break
    status_group = "Unknown"
    for group_name, group in positions["status_codes"].items():
        if group_name.startswith("***") and status_code in group.get("items", []):
            status_group = group_name
            break
    impact_group = "Unknown"
    impacts = positions.get("shared_impacts", {})
    if isinstance(impacts, dict):
        for group, sub_impacts in impacts.items():
            if group.startswith("***") and isinstance(sub_impacts, dict) and "items" in sub_impacts:
                if parts[1] and parts[1] in [impacts[code]["name"] for code in sub_impacts["items"] if code in impacts]:
                    impact_group = group
                    break
    gui_titles = positions.get("gui_titles", {})
    station_group_clean = re.sub(r'^\w\s+', '', station_group.replace('*** ', '').replace(' ***', ''))
    return (
        f"Brevity Code: {code}{' ' * 20}File: {emergency_list_mapping.get(list_id, 'Unknown')}\n"
        f"{gui_titles.get('emergency', 'Event:')} {emergency_group.replace('*** ', '').replace(' ***', '')}: {parts[0] or 'Unknown'}\n"
        f"{gui_titles.get('status', 'Status or Target:')} {status_group.replace('*** ', '').replace(' ***', '')}: {parts[4] or 'Unknown'}\n"
        f"{gui_titles.get('primary', 'Impact:')} {impact_group.replace('*** ', '').replace(' ***', '')}: {parts[1] or 'Unknown'}\n"
        f"{gui_titles.get('secondary', 'Response:')} {public_group.replace('*** ', '').replace(' ***', '')}: {parts[2] or 'Unknown'}\n"
        f"{gui_titles.get('severity', 'Station Status:')} {station_group_clean}: {parts[3] or 'Unknown'}"
    )

def generate_narrative(parts, emergency_code, primary_code, secondary_code, severity_code, status_code, code, list_id):
    emergency_group = "Unknown"
    for group, sub_emergencies in positions["emergency_type"].items():
        if group.startswith("***") and emergency_code in sub_emergencies:
            emergency_group = group
            break
        elif group == emergency_code:
            emergency_group = "Unknown"
            break
    impact_group = "Unknown"
    impacts = positions.get("shared_impacts", {})
    if isinstance(impacts, dict):
        for group, sub_impacts in impacts.items():
            if isinstance(sub_impacts, dict) and "items" in sub_impacts:
                if primary_code in sub_impacts["items"] and primary_code in impacts:
                    impact_group = group
                    break
            elif primary_code in sub_impacts:
                impact_group = group
                break
    public_group = "Unknown"
    for group_name, group in positions["public_reaction"].items():
        if isinstance(group, dict) and "items" in group and secondary_code in group.get("items", []):
            public_group = group_name
            break
    station_group = "Unknown"
    for group, sub_response in positions.get("station_response", {}).items():
        if isinstance(sub_response, dict) and "items" in sub_response:
            if severity_code in sub_response["items"] and severity_code in positions["station_response"]:
                station_group = group
                break
    status_group = "Unknown"
    for group_name, group in positions["status_codes"].items():
        if group_name.startswith("***") and status_code in group.get("items", []):
            status_group = group_name
            break
    emergency_desc = positions.get("group_descriptions", {}).get(emergency_group, "No event group description available.")
    impact_desc = positions.get("group_descriptions", {}).get(impact_group, "No impact group description available.")
    public_desc = positions["public_reaction"].get(public_group, {}).get("description", "No response group description available.")
    station_desc = positions["station_response"].get(station_group, {}).get("description", "No station status group description available.")
    status_desc = positions["status_codes"].get(status_group, {}).get("description", "No status group description available.")
    gui_titles = positions.get("gui_titles", {})
    narrative = (
        f"Brevity Code: {code} ({emergency_list_mapping.get(list_id, 'Unknown')})\n\n"
        f"{gui_titles.get('emergency', 'Event:').rstrip(':')} Group: {emergency_group.replace('*** ', '').replace(' ***', '')}\n"
        f"{emergency_desc}\n\n"
        f"{gui_titles.get('status', 'Status or Target:').rstrip(':')} Group: {status_group.replace('*** ', '').replace(' ***', '')}\n"
        f"{status_desc}\n\n"
        f"{gui_titles.get('primary', 'Impact:').rstrip(':')} Group: {impact_group.replace('*** ', '').replace(' ***', '')}\n"
        f"{impact_desc}\n\n"
        f"{gui_titles.get('secondary', 'Response:').rstrip(':')} Group: {public_group.replace('*** ', '').replace(' ***', '')}\n"
        f"{public_desc}\n\n"
        f"{gui_titles.get('severity', 'Station Status:').rstrip(':')} Group: {station_group.replace('*** ', '').replace(' ***', '')}\n"
        f"{station_desc}"
    )
    return narrative

def load_selected_file(list_id):
    global positions, current_file
    filename = emergency_list_mapping.get(list_id)
    if not filename:
        logging.warning("No valid JSON files available")
        return
    if filename == current_file:
        logging.debug(f"File {filename} already loaded, skipping")
        return
    brevity_dir = os.path.dirname(os.path.abspath(__file__))
    file_path = os.path.join(brevity_dir, filename)
    logging.info(f"Attempting to load {filename} from {file_path}")
    try:
        with open(file_path, 'r', encoding='utf-8') as f:
            data = json.load(f)
        if not validate_json_structure(data):
            logging.warning(f"Invalid JSON structure in {filename}")
            return
        positions = data
        current_file = filename
        # Only update GUI elements if they are defined
        if gui_widgets:
            gui_titles = positions.get("gui_titles", {})
            gui_widgets['label_select'].setText(gui_titles.get("select_list", "1. Select List:"))
            gui_widgets['label_emergency'].setText(gui_titles.get("emergency", "2. Event:"))
            gui_widgets['label_status'].setText(gui_titles.get("status", "3. Status/Target:"))
            gui_widgets['label_primary'].setText(gui_titles.get("primary", "4. Impact:"))
            gui_widgets['label_secondary'].setText(gui_titles.get("secondary", "5. Response:"))
            gui_widgets['label_severity'].setText(gui_titles.get("severity", "6. Station/Location:"))
            gui_widgets['list_combo'].setCurrentText(filename)
            gui_widgets['emergency_combo'].setCurrentText("Select Code")
            gui_widgets['status_combo'].setCurrentText("Select Code")
            gui_widgets['primary_combo'].setCurrentText("Select Code")
            gui_widgets['secondary_combo'].setCurrentText("Select Code")
            gui_widgets['severity_combo'].setCurrentText("Select Code")
            gui_widgets['output_text'].clear()
            gui_widgets['narrative_text'].clear()
            first_emergency_code = sorted([k for k in positions["emergency_type"].keys() if not k.startswith("***")])[0] if positions["emergency_type"] else "A"
            update_menus(first_emergency_code)
            show_status_message(f"Loaded {filename}", 5000)
    except FileNotFoundError:
        logging.error(f"File not found: {filename}")
    except json.JSONDecodeError as e:
        logging.error(f"Invalid JSON in {filename}: {str(e)}")
    except Exception as e:
        logging.error(f"Error loading {filename}: {str(e)}")

def validate_code_input(new_value):
    if len(new_value) > 6:
        return False
    return bool(re.match(r'^[0-9]?[A-Za-z]?[A-Za-z]?[A-Za-z]*$', new_value))

def decode_code(event=None):
    """Decode a brevity code using PyQt5 widgets from gui_widgets dict"""
    decode_entry = gui_widgets.get('decode_entry')
    output_text = gui_widgets.get('output_text')
    narrative_text = gui_widgets.get('narrative_text')
    list_combo = gui_widgets.get('list_combo')
    emergency_combo = gui_widgets.get('emergency_combo')
    status_combo = gui_widgets.get('status_combo')
    primary_combo = gui_widgets.get('primary_combo')
    secondary_combo = gui_widgets.get('secondary_combo')
    severity_combo = gui_widgets.get('severity_combo')
    
    code = (decode_entry.text().strip().upper() if decode_entry else "").strip()
    
    if not re.match(r'^[0-9][A-Z]{5}$', code):
        show_status_message(f"Invalid code: Use format #AAAAA", 10000)
        logging.warning(f"Invalid code format: {code}")
        if output_text:
            output_text.clear()
        if narrative_text:
            narrative_text.clear()
        return f"Invalid code: Use format #AAAAA"
    
    list_id = code[0]
    emergency_code = code[1]
    status_code = code[2]
    primary_code = code[3]
    secondary_code = code[4]
    severity_code = code[5]
    
    if list_id not in emergency_list_mapping:
        show_status_message(f"Invalid list ID: {list_id}", 10000)
        logging.warning(f"Invalid list ID: {list_id}")
        return f"Invalid list ID: {list_id}"
    
    current_file_selected = list_combo.currentText() if list_combo else ""
    expected_file = emergency_list_mapping[list_id]
    if current_file_selected != expected_file:
        logging.debug(f"Mismatch in selected file. Expected {expected_file}, loading")
        load_selected_file(list_id)
    if list_combo is not None:
        list_combo.setCurrentText(expected_file)
    
    if not positions:
        show_status_message("No event list loaded", 10000)
        logging.warning("No positions data loaded")
        return "No event list loaded"
    
    try:
        logging.debug(f"positions keys: {list(positions.keys())}")
        logging.debug(f"station_response: {positions.get('station_response', {})}")
        logging.debug(f"Checking severity_code: {severity_code}")
        
        emergency_data = None
        emergency_group = "Unknown"
        has_groups = any(k.startswith("***") for k in positions["emergency_type"].keys())
        if has_groups:
            for group, sub_emergencies in positions["emergency_type"].items():
                if group.startswith("***") and emergency_code in sub_emergencies:
                    emergency_data = sub_emergencies[emergency_code]
                    emergency_group = group
                    break
                elif group == emergency_code:
                    emergency_data = positions["emergency_type"][emergency_code]
                    emergency_group = "Unknown"
                    break
        else:
            if emergency_code in positions["emergency_type"]:
                emergency_data = positions["emergency_type"][emergency_code]
                emergency_group = "Unknown"
        
        if not emergency_data:
            show_status_message(f"Invalid Event Type code: {emergency_code}", 10000)
            logging.warning(f"Invalid Event Type code: {emergency_code}")
            return f"Invalid Event Type code: {emergency_code}"
        
        impacts = positions.get("shared_impacts", {})
        valid_primary_code = False
        primary_impact_name = None
        impact_group = "Unknown"
        if isinstance(impacts, dict):
            if primary_code in impacts and isinstance(impacts[primary_code], dict) and "name" in impacts[primary_code]:
                valid_primary_code = True
                primary_impact_name = impacts[primary_code]["name"]
                impact_group = impacts[primary_code].get("group", "Unknown")
            else:
                for group, sub_impacts in impacts.items():
                    if isinstance(sub_impacts, dict) and "items" in sub_impacts:
                        if primary_code in sub_impacts["items"] and primary_code in impacts:
                            valid_primary_code = True
                            primary_impact_name = impacts[primary_code]["name"]
                            impact_group = group
                            break
        
        if not valid_primary_code:
            show_status_message(f"Invalid Impact code: {primary_code}", 10000)
            logging.warning(f"Invalid Impact code: {primary_code}")
            return f"Invalid Impact code: {primary_code}"
        
        if secondary_code not in positions["public_reaction"]:
            show_status_message(f"Invalid Response code: {secondary_code}", 10000)
            logging.warning(f"Invalid Response code: {secondary_code}")
            return f"Invalid Response code: {secondary_code}"
        
        station_response = positions.get("station_response", {})
        valid_severity_code = False
        severity_name = "Unknown"
        if severity_code in station_response and isinstance(station_response[severity_code], dict) and "name" in station_response[severity_code]:
            valid_severity_code = True
            severity_name = station_response[severity_code]["name"]
        else:
            for group, sub_response in station_response.items():
                if isinstance(sub_response, dict) and "items" in sub_response:
                    if severity_code in sub_response["items"] and severity_code in station_response:
                        valid_severity_code = True
                        severity_name = station_response[severity_code].get("name", "Unknown")
                        break
        
        if not valid_severity_code:
            show_status_message(f"Invalid Station Status code: {severity_code}", 10000)
            logging.warning(f"Invalid Station Status code: {severity_code}")
            return f"Invalid Station Status code: {severity_code}"
        
        if status_code not in positions["status_codes"]:
            show_status_message(f"Invalid Status/Target code: {status_code}", 10000)
            logging.warning(f"Invalid Status/Target code: {status_code}")
            return f"Invalid Status/Target code: {status_code}"
        
        def set_combo_by_code(combo, target_code):
            if combo is None: return
            for i in range(combo.count()):
                text = combo.itemText(i).strip()
                if text.startswith(f"{target_code}-"):
                    combo.setCurrentIndex(i)
                    return
                    
        # Set combos in exact cascading order so they override the resets
        set_combo_by_code(emergency_combo, emergency_code)
        set_combo_by_code(status_combo, status_code)
        set_combo_by_code(primary_combo, primary_code)
        set_combo_by_code(secondary_combo, secondary_code)
        set_combo_by_code(severity_combo, severity_code)
        
        description_parts = [
            emergency_data["name"] if emergency_code != "A" else None,
            primary_impact_name if primary_code != "A" else None,
            positions["public_reaction"][secondary_code]["name"] if secondary_code != "A" else None,
            severity_name if severity_code != "A" else None,
            positions["status_codes"][status_code]["name"] if status_code in positions["status_codes"] else "Unknown"
        ]
        description = generate_description(description_parts, severity_code, list_id, code, status_code, secondary_code, emergency_group, impact_group)
        narrative = generate_narrative(description_parts, emergency_code, primary_code, secondary_code, severity_code, status_code, code, list_id)
        
        if output_text:
            output_text.setPlainText(description)
        if narrative_text:
            narrative_text.setPlainText(narrative)
        
        show_status_message("Brevity code generated", 5000)
        return description
    except Exception as e:
        logging.error(f"Error decoding code: {str(e)}")
        show_status_message(f"Error decoding code: {str(e)}", 10000)
        return f"Error decoding code: {str(e)}"


def decode_to_report(code):
    """Decode a brevity code and return the Brevity Report as a string."""
    global emergency_list_mapping, positions, current_file, gui_widgets
    emergency_list_mapping = get_json_files()
    if not emergency_list_mapping:
        return "Error: No valid JSON files found"
    code = code.strip().upper()
    # Create a mock decode_entry object
    class MockEntry:
        def text(self):
            return code
    # Temporarily replace gui_widgets
    old_widgets = gui_widgets.copy() if gui_widgets else {}
    gui_widgets['decode_entry'] = MockEntry()
    gui_widgets['output_text'] = None
    gui_widgets['narrative_text'] = None
    gui_widgets['list_combo'] = None
    gui_widgets['emergency_combo'] = None
    gui_widgets['status_combo'] = None
    gui_widgets['primary_combo'] = None
    gui_widgets['secondary_combo'] = None
    gui_widgets['severity_combo'] = None
    
    result = decode_code()
    
    # Restore gui_widgets
    if old_widgets:
        gui_widgets.update(old_widgets)
    return result

def clear_fields():
    global updating_menus
    updating_menus = False
    gui_widgets['list_combo'].setCurrentText("Select Emergency List")
    gui_widgets['emergency_combo'].setCurrentText("Select Code")
    gui_widgets['status_combo'].setCurrentText("Select Code")
    gui_widgets['primary_combo'].setCurrentText("Select Code")
    gui_widgets['secondary_combo'].setCurrentText("Select Code")
    gui_widgets['severity_combo'].setCurrentText("Select Code")
    gui_widgets['output_text'].clear()
    gui_widgets['narrative_text'].clear()
    if 'decode_entry' in gui_widgets:
        gui_widgets['decode_entry'].clear()
    show_status_message("Fields cleared", 5000)
    logging.debug("Cleared all fields and outputs")

def populate_combo(combo, data, key, max_length=100, group_order=None, emergency_code=None):
    """Populate a QComboBox with data from JSON structure"""
    current_text = combo.currentText().strip()
    
    combo.blockSignals(True)
    combo.clear()
    combo.addItem("Select Code")
    
    if not data:
        combo.addItem(f"No {key} Available")
        for i in range(combo.count()):
            if combo.itemText(i).strip() == current_text:
                combo.setCurrentIndex(i)
                break
        combo.blockSignals(False)
        return
    
    if "A" in data and key != "status":
        val = f"A-{data['A'].get('name', 'Unknown')}"
        combo.addItem(val)
        combo.insertSeparator(combo.count())
    
    has_groups = any(k.startswith("***") for k in data.keys())
    if has_groups and group_order:
        for group in group_order:
            if group in data:
                combo.addItem(group)
                # Disable group headers
                model = combo.model()
                item = model.item(combo.count() - 1)
                item.setEnabled(False)
                from PyQt5.QtGui import QFont, QColor
                font = QFont()
                font.setBold(True)
                item.setFont(font)
                item.setForeground(QColor(theme.group_header_color()))
                
                group_data = data[group]
                codes_in_group = []
                if "items" in group_data and isinstance(group_data["items"], list):
                    codes_in_group = [c for c in sorted(group_data["items"]) if c in data and isinstance(data[c], dict) and "name" in data[c]]
                else:
                    codes_in_group = sorted([c for c in group_data.keys() if re.match(r'^[A-Z]$', c)])
                for code in codes_in_group:
                    name = data.get(code, {}).get('name', 'Unknown') if key == "impacts" else group_data.get(code, {}).get('name', 'Unknown')
                    val = f"{code}-{name}"
                    combo.addItem(" " + val)
                combo.insertSeparator(combo.count())
    else:
        for code in sorted(data.keys()):
            if code == "A" or code.startswith("***"): continue
            val = f"{code}-{data[code].get('name', 'Unknown')}"
            combo.addItem(val)
    
    for i in range(combo.count()):
        if combo.itemText(i).strip() == current_text:
            combo.setCurrentIndex(i)
            break
            
    combo.blockSignals(False)


def update_menus(emergency_code, primary_code=None):
    """Update all combo boxes based on current selections"""
    global updating_menus
    if updating_menus:
        logging.debug("Skipping update_menus: already in progress")
        return
    updating_menus = True
    try:
        logging.debug(f"Updating menus for emergency_code={emergency_code}")
        max_length = 100
        
        # Update emergency combo
        if 'emergency_combo' in gui_widgets:
            emergency_combo = gui_widgets['emergency_combo']
            current_text = emergency_combo.currentText().strip()
            emergency_combo.blockSignals(True)
            emergency_combo.clear()
            emergency_combo.addItem("Select Code")
            if not positions:
                emergency_combo.addItem("No Event List Loaded")
            else:
                populate_combo(emergency_combo, positions["emergency_type"], "emergency_type",
                              max_length, positions.get("emergency_group_order", []),
                              emergency_code)
            for i in range(emergency_combo.count()):
                if emergency_combo.itemText(i).strip() == current_text:
                    emergency_combo.setCurrentIndex(i)
                    break
            emergency_combo.blockSignals(False)
        
        # Update primary combo
        if 'primary_combo' in gui_widgets:
            primary_combo = gui_widgets['primary_combo']
            populate_combo(primary_combo, positions.get("shared_impacts", {}), "impacts",
                          max_length, positions.get("impact_group_order", []),
                          emergency_code)
        
        # Update secondary combo
        if 'secondary_combo' in gui_widgets:
            secondary_combo = gui_widgets['secondary_combo']
            current_text = secondary_combo.currentText().strip()
            secondary_combo.blockSignals(True)
            secondary_combo.clear()
            secondary_combo.addItem("Select Code")
            if not positions.get("public_reaction", {}):
                secondary_combo.addItem("No Response Available")
            else:
                if "A" in positions["public_reaction"]:
                    val = f"A-{positions['public_reaction']['A']['name']}"
                    secondary_combo.addItem(val)
                    secondary_combo.insertSeparator(secondary_combo.count())
                for group_name in sorted(positions["public_reaction"].keys(), key=lambda x: positions["public_reaction"][x].get("order", float("inf")) if isinstance(positions["public_reaction"][x], dict) and "order" in positions["public_reaction"][x] else float("inf")):
                    if not group_name.startswith("***"): continue
                    group = positions["public_reaction"][group_name]
                    secondary_combo.addItem(group_name)
                    # Disable group headers
                    model = secondary_combo.model()
                    item = model.item(secondary_combo.count() - 1)
                    item.setEnabled(False)
                    from PyQt5.QtGui import QFont, QColor
                    font = QFont()
                    font.setBold(True)
                    item.setFont(font)
                    item.setForeground(QColor(theme.group_header_color()))
                    
                    for code in sorted(group.get("items", [])):
                        if code in positions["public_reaction"]:
                            val = f"{code}-{positions['public_reaction'][code].get('name', 'Unknown')}"
                            secondary_combo.addItem(" " + val)
                    secondary_combo.insertSeparator(secondary_combo.count())
                unmapped_items = [code for code in sorted(positions["public_reaction"].keys()) if code != "A" and code != "Y" and not code.startswith("***") and not any(code in group.get("items", []) for group in positions["public_reaction"].values() if isinstance(group, dict) and "items" in group)]
                if unmapped_items:
                    secondary_combo.insertSeparator(secondary_combo.count())
                    for code in sorted(unmapped_items):
                        val = f"{code}-{positions['public_reaction'][code].get('name', 'Unknown')}"
                        secondary_combo.addItem(val)
            for i in range(secondary_combo.count()):
                if secondary_combo.itemText(i).strip() == current_text:
                    secondary_combo.setCurrentIndex(i)
                    break
            secondary_combo.blockSignals(False)
        
        # Update severity combo
        if 'severity_combo' in gui_widgets:
            severity_combo = gui_widgets['severity_combo']
            current_text = severity_combo.currentText().strip()
            severity_combo.blockSignals(True)
            severity_combo.clear()
            severity_combo.addItem("Select Code")
            if not positions.get("station_response", {}):
                severity_combo.addItem("No Station Status Available")
            else:
                if "A" in positions["station_response"] and not positions["station_response"]["A"].get("group"):
                    val = f"A-{positions['station_response']['A'].get('name', 'Unknown')}"
                    severity_combo.addItem(val)
                    severity_combo.insertSeparator(severity_combo.count())
                for group_name, group in sorted(positions["station_response"].items(), key=lambda x: x[1].get("order", float("inf")) if isinstance(x[1], dict) and "order" in x[1] else float("inf")):
                    if not group_name.startswith("***"): continue
                    severity_combo.addItem(group_name)
                    # Disable group headers
                    model = severity_combo.model()
                    item = model.item(severity_combo.count() - 1)
                    item.setEnabled(False)
                    from PyQt5.QtGui import QFont, QColor
                    font = QFont()
                    font.setBold(True)
                    item.setFont(font)
                    item.setForeground(QColor(theme.group_header_color()))
                    
                    response_dict = positions["station_response"]
                    for code in sorted(group.get("items", [])):
                        if code in response_dict:
                            name = response_dict[code].get('name', 'Unknown')
                            val = f"{code}-{name}"
                            severity_combo.addItem(" " + val)
                    severity_combo.insertSeparator(severity_combo.count())
            for i in range(severity_combo.count()):
                if severity_combo.itemText(i).strip() == current_text:
                    severity_combo.setCurrentIndex(i)
                    break
            severity_combo.blockSignals(False)
        
        # Update status combo
        if 'status_combo' in gui_widgets:
            status_combo = gui_widgets['status_combo']
            current_text = status_combo.currentText().strip()
            status_combo.blockSignals(True)
            status_combo.clear()
            status_combo.addItem("Select Code")
            if not positions.get("status_codes"):
                status_combo.addItem("No Status/Target List Loaded")
                logging.debug("No valid status codes available, using default label")
            else:
                status_group_order = sorted(
                    [g for g in positions["status_codes"].keys() if g.startswith("***")],
                    key=lambda x: positions["status_codes"][x].get("order", float("inf"))
                )
                codes = {k: v for k, v in positions["status_codes"].items() if not k.startswith("***")}
                standalone_codes = [code for code in sorted(codes.keys()) if not any(code in group.get("items", []) for group in positions["status_codes"].values() if group.get("items"))]
                for code in standalone_codes:
                    val = f"{code}-{codes[code].get('name', 'Unknown')}"
                    status_combo.addItem(val)
                if standalone_codes:
                    status_combo.insertSeparator(status_combo.count())
                for group_name in status_group_order:
                    if group_name in positions["status_codes"]:
                        status_combo.addItem(group_name)
                        # Disable group headers
                        model = status_combo.model()
                        item = model.item(status_combo.count() - 1)
                        item.setEnabled(False)
                        from PyQt5.QtGui import QFont, QColor
                        font = QFont()
                        font.setBold(True)
                        item.setFont(font)
                        item.setForeground(QColor(theme.group_header_color()))
                        
                        for code in sorted(positions["status_codes"][group_name].get("items", [])):
                            if code in codes:
                                val = f"{code}-{codes[code].get('name', 'Unknown')}"
                                status_combo.addItem(" " + val)
            for i in range(status_combo.count()):
                if status_combo.itemText(i).strip() == current_text:
                    status_combo.setCurrentIndex(i)
                    break
            status_combo.blockSignals(False)
    finally:
        updating_menus = False



def handle_menu_select(key, text):
    """Handle combo box selection changes"""
    if text == "Select Code" or text == "Select Emergency List":
        logging.debug(f"Ignoring 'Select Code' selection for key={key}")
        return
    
    # Extract code from text (format: "X-Name")
    code = text.split("-")[0].strip() if "-" in text else text
    
    logging.debug(f"Handling menu selection: key={key}, code={code}, text={text}")
    
    if key == "list":
        gui_widgets['emergency_combo'].setCurrentText("Select Code")
        gui_widgets['status_combo'].setCurrentText("Select Code")
        gui_widgets['primary_combo'].setCurrentText("Select Code")
        gui_widgets['secondary_combo'].setCurrentText("Select Code")
        gui_widgets['severity_combo'].setCurrentText("Select Code")
        gui_widgets['output_text'].clear()
        gui_widgets['narrative_text'].clear()
        
        # Load the selected file
        for list_id, filename in emergency_list_mapping.items():
            if filename == text:
                load_selected_file(list_id)
                break
        update_menus("A")
    elif key == "emergency":
        gui_widgets['status_combo'].setCurrentText("Select Code")
        gui_widgets['primary_combo'].setCurrentText("Select Code")
        gui_widgets['secondary_combo'].setCurrentText("Select Code")
        gui_widgets['severity_combo'].setCurrentText("Select Code")
        gui_widgets['output_text'].clear()
        gui_widgets['narrative_text'].clear()
    elif key == "status":
        gui_widgets['primary_combo'].setCurrentText("Select Code")
        gui_widgets['secondary_combo'].setCurrentText("Select Code")
        gui_widgets['severity_combo'].setCurrentText("Select Code")
        gui_widgets['output_text'].clear()
        gui_widgets['narrative_text'].clear()
        
        # Find group for status code
        group = None
        for group_name, group_data in positions["status_codes"].items():
            if group_name.startswith("***") and isinstance(group_data, dict) and "items" in group_data:
                if code in group_data.get("items", []):
                    group = group_name
                    break
        
        if group:
            group_description = positions["status_codes"].get(group, {}).get("description", "No group description available")
            gui_widgets['narrative_text'].setPlainText(group_description)
        
    elif key == "primary":
        gui_widgets['secondary_combo'].setCurrentText("Select Code")
        gui_widgets['severity_combo'].setCurrentText("Select Code")
        gui_widgets['output_text'].clear()
        gui_widgets['narrative_text'].clear()
        
    elif key == "secondary":
        gui_widgets['severity_combo'].setCurrentText("Select Code")
        gui_widgets['output_text'].clear()
        gui_widgets['narrative_text'].clear()
        
        # Find group for secondary code
        group = None
        for group_name, group_data in positions["public_reaction"].items():
            if group_name.startswith("***") and isinstance(group_data, dict) and "items" in group_data:
                if code in group_data.get("items", []):
                    group = group_name
                    break
        
        if group:
            group_description = positions["public_reaction"].get(group, {}).get("description", "No response group description available")
            gui_widgets['narrative_text'].setPlainText(group_description)
        elif code == "A":
            gui_widgets['narrative_text'].setPlainText("No group description for Unknown")
        
    elif key == "severity":
        gui_widgets['output_text'].clear()
        gui_widgets['narrative_text'].clear()
        
        # Find group for severity code
        group = None
        for group_name, group_data in positions["station_response"].items():
            if group_name.startswith("***") and isinstance(group_data, dict) and "items" in group_data:
                if code in group_data.get("items", []):
                    group = group_name
                    break
        
        if group:
            group_description = positions["station_response"].get(group, {}).get("description", "No station status group description available")
            gui_widgets['narrative_text'].setPlainText(group_description)
        elif code == "A":
            gui_widgets['narrative_text'].setPlainText("No group description for Unknown")
        
    
    on_field_change()

def copy_code_text(copy_full_description=False):
    """Copy brevity code or full description to clipboard"""
    try:
        from PyQt5.QtWidgets import QApplication
        text = gui_widgets['output_text'].toPlainText()
        if not text or not text.startswith("Brevity Code:"):
            show_status_message("No brevity code available to copy", 10000)
            logging.debug("No brevity code available")
            return
        first_line = text.split('\n')[0]
        code = first_line[13:].split("File:")[0].strip()
        if not code:
            show_status_message("No brevity code available to copy", 10000)
            logging.debug("Empty brevity code")
            return
        text_to_copy = text if copy_full_description else code
        QApplication.clipboard().setText(text_to_copy)
        show_status_message("Code copied to clipboard", 5000)
        logging.debug(f"Copied {'full description' if copy_full_description else 'code'}")
    except Exception as e:
        show_status_message(f"Error copying code: {str(e)}", 10000)
        logging.debug(f"Error copying code: {str(e)}")

def copy_all():
    """Copy both output and narrative to clipboard"""
    try:
        from PyQt5.QtWidgets import QApplication
        output = gui_widgets['output_text'].toPlainText()
        narrative = gui_widgets['narrative_text'].toPlainText()
        if not output and not narrative:
            show_status_message("No output or narrative available to copy", 10000)
            logging.debug("No output or narrative available")
            return
        combined_text = output
        if narrative:
            combined_text += "\n\n" + narrative
        QApplication.clipboard().setText(combined_text)
        show_status_message("Output and narrative copied to clipboard", 5000)
        logging.debug("Copied output and narrative")
    except Exception as e:
        show_status_message(f"Error copying output and narrative: {str(e)}", 10000)
        logging.debug(f"Error copying output and narrative: {str(e)}")

def copy_sitrep():
    """Copy situation report to clipboard"""
    try:
        from PyQt5.QtWidgets import QApplication
        sitrep_text = gui_widgets['output_text'].toPlainText()
        if not sitrep_text:
            show_status_message("No Situation Report available to copy", 10000)
            logging.debug("No Situation Report available")
            return
        QApplication.clipboard().setText(sitrep_text)
        show_status_message("Situation Report copied to clipboard", 5000)
        logging.debug("Copied Situation Report")
    except Exception as e:
        show_status_message(f"Error copying Situation Report: {str(e)}", 10000)
        logging.debug(f"Error copying Situation Report: {str(e)}")

def toggle_narrative():
    """Toggle narrative section visibility"""
    if gui_widgets['narrative_check'].isChecked():
        gui_widgets['narrative_label'].show()
        gui_widgets['narrative_frame'].show()
    else:
        gui_widgets['narrative_frame'].hide()
        gui_widgets['narrative_label'].hide()

def paste_into_decode():
    """Paste from clipboard into decode entry and decode"""
    try:
        from PyQt5.QtWidgets import QApplication
        clipboard = QApplication.clipboard().text()
        gui_widgets['decode_entry'].setText(clipboard)
        decode_code()
    except Exception as e:
        show_status_message("Clipboard is empty or invalid", 5000)

def on_field_change(*args):
    """Generate brevity code when all fields are selected"""
    if not positions:
        show_status_message("No event list loaded", 10000)
        logging.warning("No positions data loaded")
        gui_widgets['output_text'].clear()
        gui_widgets['narrative_text'].clear()
        return
    
    list_id = None
    list_text = gui_widgets['list_combo'].currentText()
    for lid, fname in emergency_list_mapping.items():
        if list_text == fname:
            list_id = lid
            break
    if not list_id or list_text == "Select Emergency List":
        show_status_message("No event list selected", 10000)
        logging.warning("No valid list_id or Select Emergency List selected")
        gui_widgets['output_text'].clear()
        gui_widgets['narrative_text'].clear()
        return
    
    emergency_val = gui_widgets['emergency_combo'].currentText()
    status_val = gui_widgets['status_combo'].currentText()
    primary_val = gui_widgets['primary_combo'].currentText()
    secondary_val = gui_widgets['secondary_combo'].currentText()
    severity_val = gui_widgets['severity_combo'].currentText()
    
    if any(val == "Select Code" for val in [emergency_val, status_val, primary_val, secondary_val, severity_val]):
        logging.debug("Incomplete selection")
        return
    
    try:
        emergency_code = emergency_val.split("-")[0].strip()
        status_code = status_val.split("-")[0].strip()
        primary_code = primary_val.split("-")[0].strip()
        secondary_code = secondary_val.split("-")[0].strip()
        severity_code = severity_val.split("-")[0].strip()
        
        emergency_data = None
        emergency_group = "Unknown"
        has_groups = any(k.startswith("***") for k in positions["emergency_type"].keys())
        if has_groups:
            for group, sub_emergencies in positions["emergency_type"].items():
                if group.startswith("***") and emergency_code in sub_emergencies:
                    emergency_data = sub_emergencies[emergency_code]
                    emergency_group = group
                    break
                elif group == emergency_code:
                    emergency_data = positions["emergency_type"][emergency_code]
                    emergency_group = "Unknown"
                    break
        else:
            if emergency_code in positions["emergency_type"]:
                emergency_data = positions["emergency_type"][emergency_code]
                emergency_group = "Unknown"
        if not emergency_data:
            show_status_message(f"Invalid Event Type code: {emergency_code}", 10000)
            logging.warning(f"Invalid Event Type code: {emergency_code}")
            return
        
        impacts = positions.get("shared_impacts", {})
        valid_primary_code = False
        primary_impact_name = "Unknown"
        impact_group = "Unknown"
        if isinstance(impacts, dict):
            if primary_code in impacts and isinstance(impacts[primary_code], dict) and "name" in impacts[primary_code]:
                valid_primary_code = True
                primary_impact_name = impacts[primary_code]["name"]
                impact_group = impacts[primary_code].get("group", "Unknown")
            else:
                for group, sub_impacts in impacts.items():
                    if isinstance(sub_impacts, dict) and "items" in sub_impacts:
                        if primary_code in sub_impacts["items"] and primary_code in impacts:
                            valid_primary_code = True
                            primary_impact_name = impacts[primary_code]["name"]
                            impact_group = group
                            break
        if not valid_primary_code:
            show_status_message(f"Invalid Impact code: {primary_code}", 10000)
            logging.warning(f"Invalid Impact code: {primary_code}")
            return
        
        if secondary_code not in positions["public_reaction"]:
            show_status_message(f"Invalid Response code: {secondary_code}", 10000)
            logging.warning(f"Invalid Response code: {secondary_code}")
            return
        
        station_response = positions.get("station_response", {})
        valid_severity_code = False
        severity_name = "Unknown"
        if severity_code in station_response and isinstance(station_response[severity_code], dict):
            valid_severity_code = True
            severity_name = station_response[severity_code].get("name", "Unknown")
        else:
            for group, sub_response in station_response.items():
                if isinstance(sub_response, dict) and "items" in sub_response:
                    if severity_code in sub_response["items"]:
                        valid_severity_code = True
                        if severity_code in station_response and isinstance(station_response[severity_code], dict):
                            severity_name = station_response[severity_code].get("name", "Unknown")
                        break
                elif severity_code in sub_response:
                    valid_severity_code = True
                    severity_name = sub_response[severity_code].get("name", "Unknown")
                    break
        if not valid_severity_code:
            logging.warning(f"Invalid Station Status code: {severity_code}")
            show_status_message(f"Invalid Station Status code: {severity_code}", 10000)
            return
        
        if status_code not in positions["status_codes"]:
            show_status_message(f"Invalid Status/Target code: {status_code}", 10000)
            logging.warning(f"Invalid Status/Target code: {status_code}")
            return
        
        code = f"{list_id}{emergency_code}{status_code}{primary_code}{secondary_code}{severity_code}"
        description_parts = [
            emergency_data["name"] if emergency_code != "A" else None,
            primary_impact_name if primary_code != "A" else None,
            positions["public_reaction"][secondary_code]["name"] if secondary_code != "A" else None,
            severity_name if severity_code != "A" else None,
            positions["status_codes"][status_code]["name"] if status_code in positions["status_codes"] else "Unknown"
        ]
        description = generate_description(description_parts, severity_code, list_id, code, status_code, secondary_code, emergency_group, impact_group)
        narrative = generate_narrative(description_parts, emergency_code, primary_code, secondary_code, severity_code, status_code, code, list_id)
        
        gui_widgets['output_text'].setPlainText(description)
        gui_widgets['narrative_text'].setPlainText(narrative)
        show_status_message("Brevity code generated", 5000)
    except Exception as e:
        logging.error(f"Error generating code: {str(e)}")
        gui_widgets['output_text'].clear()
        gui_widgets['narrative_text'].clear()



if __name__ == "__main__":
    try:
        from PyQt5.QtWidgets import (QApplication, QMainWindow, QWidget, QVBoxLayout, QHBoxLayout, 
                                     QLabel, QLineEdit, QPushButton, QComboBox, QTextEdit, 
                                     QFrame, QCheckBox, QStatusBar, QAction, QMenu, QListView)
        from PyQt5.QtCore import Qt, QRegExp
        from PyQt5.QtGui import QFont, QRegExpValidator, QIcon
        from theme_manager import theme
        
        app = QApplication(sys.argv)
        
        # Set window icon if available
        if os.path.exists("radiation-32.png"):
            app.setWindowIcon(QIcon("radiation-32.png"))
        
        window = QMainWindow()
        window.setWindowTitle("Brevity1.0 by KD9DSS")
        window.resize(700, 750)
        
        # Apply theme colors
        window.setStyleSheet(f"""
            QMainWindow {{
                background-color: {theme.main_window_bg()};
                color: {theme.color('windowtext')};
            }}
            QLabel {{
                color: {theme.color('text')};
                font-weight: bold;
                font-size: 10pt;
            }}
            QLineEdit {{
                background-color: {theme.color('base')};
                color: {theme.color('text')};
                border: 1px solid {theme.color('mid')};
                padding: 4px;
                font-size: 10pt;
            }}
            {theme.combo_data_style()}
            {theme.combo_list_data_style()}
            QTextEdit {{
                background-color: {theme.color('base')};
                color: {theme.color('text')};
                border: 1px solid {theme.color('mid')};
                font-size: 12pt;
            }}
            QFrame {{
                border: 1px solid {theme.color('mid')};
            }}
            QCheckBox {{
                color: {theme.color('text')};
                font-weight: bold;
                font-size: 10pt;
            }}
        """)
        
        # Create central widget and main layout
        central_widget = QWidget()
        window.setCentralWidget(central_widget)
        main_layout = QVBoxLayout(central_widget)
        main_layout.setSpacing(10)
        main_layout.setContentsMargins(10, 10, 10, 10)
        
        # Top section - Decode area
        decode_frame = QFrame()
        decode_layout = QVBoxLayout(decode_frame)
        decode_layout.setAlignment(Qt.AlignCenter)
        
        label_decode = QLabel("Enter Brevity Code:")
        label_decode.setAlignment(Qt.AlignCenter)
        label_decode.setStyleSheet(theme.field_title_style())
        decode_layout.addWidget(label_decode)
        
        decode_inner_layout = QHBoxLayout()
        decode_inner_layout.setAlignment(Qt.AlignCenter)
        
        decode_entry = QLineEdit()
        decode_entry.setMaxLength(6)
        decode_entry.setFixedWidth(140)
        validator = QRegExpValidator(QRegExp("[0-9]?[A-Za-z]{0,5}"))
        decode_entry.setValidator(validator)
        decode_inner_layout.addWidget(decode_entry)
        
        decode_button = QPushButton("Decode")
        decode_button.setFixedWidth(100)
        decode_button.setStyleSheet(theme.button_style("#28a745"))
        decode_inner_layout.addWidget(decode_button)
        
        decode_layout.addLayout(decode_inner_layout)
        main_layout.addWidget(decode_frame)
        
        # Input frame - 6 dropdowns in 2 rows
        input_frame = QFrame()
        input_frame.setFrameStyle(QFrame.Box | QFrame.Plain)
        input_layout = QVBoxLayout(input_frame)
        
        # Row 1: List, Emergency, Status
        row1_layout = QHBoxLayout()
        row1_layout.setSpacing(10)
        
        # List selector
        list_subframe = QWidget()
        list_sublayout = QVBoxLayout(list_subframe)
        list_sublayout.setContentsMargins(0, 0, 0, 0)
        label_select = QLabel("1. Select List:")
        label_select.setAlignment(Qt.AlignCenter)
        label_select.setStyleSheet(theme.field_title_style())
        list_sublayout.addWidget(label_select)
        list_combo = QComboBox()
        list_combo.setView(QListView())
        list_combo.addItem("Select Emergency List")
        list_sublayout.addWidget(list_combo)
        row1_layout.addWidget(list_subframe)
        
        # Emergency selector
        emergency_subframe = QWidget()
        emergency_sublayout = QVBoxLayout(emergency_subframe)
        emergency_sublayout.setContentsMargins(0, 0, 0, 0)
        label_emergency = QLabel("2. Event:")
        label_emergency.setAlignment(Qt.AlignCenter)
        label_emergency.setStyleSheet(theme.field_title_style())
        emergency_sublayout.addWidget(label_emergency)
        emergency_combo = QComboBox()
        emergency_combo.setView(QListView())
        emergency_combo.addItem("Select Code")
        emergency_sublayout.addWidget(emergency_combo)
        row1_layout.addWidget(emergency_subframe)
        
        # Status selector
        status_subframe = QWidget()
        status_sublayout = QVBoxLayout(status_subframe)
        status_sublayout.setContentsMargins(0, 0, 0, 0)
        label_status = QLabel("3. Status/Target:")
        label_status.setAlignment(Qt.AlignCenter)
        label_status.setStyleSheet(theme.field_title_style())
        status_sublayout.addWidget(label_status)
        status_combo = QComboBox()
        status_combo.setView(QListView())
        status_combo.addItem("Select Code")
        status_sublayout.addWidget(status_combo)
        row1_layout.addWidget(status_subframe)
        
        input_layout.addLayout(row1_layout)
        
        # Row 2: Primary, Secondary, Severity
        row2_layout = QHBoxLayout()
        row2_layout.setSpacing(10)
        
        # Primary selector
        primary_subframe = QWidget()
        primary_sublayout = QVBoxLayout(primary_subframe)
        primary_sublayout.setContentsMargins(0, 0, 0, 0)
        label_primary = QLabel("4. Impact:")
        label_primary.setAlignment(Qt.AlignCenter)
        label_primary.setStyleSheet(theme.field_title_style())
        primary_sublayout.addWidget(label_primary)
        primary_combo = QComboBox()
        primary_combo.setView(QListView())
        primary_combo.addItem("Select Code")
        primary_sublayout.addWidget(primary_combo)
        row2_layout.addWidget(primary_subframe)
        
        # Secondary selector
        secondary_subframe = QWidget()
        secondary_sublayout = QVBoxLayout(secondary_subframe)
        secondary_sublayout.setContentsMargins(0, 0, 0, 0)
        label_secondary = QLabel("5. Response:")
        label_secondary.setAlignment(Qt.AlignCenter)
        label_secondary.setStyleSheet(theme.field_title_style())
        secondary_sublayout.addWidget(label_secondary)
        secondary_combo = QComboBox()
        secondary_combo.setView(QListView())
        secondary_combo.addItem("Select Code")
        secondary_sublayout.addWidget(secondary_combo)
        row2_layout.addWidget(secondary_subframe)
        
        # Severity selector
        severity_subframe = QWidget()
        severity_sublayout = QVBoxLayout(severity_subframe)
        severity_sublayout.setContentsMargins(0, 0, 0, 0)
        label_severity = QLabel("6. Station/Location:")
        label_severity.setAlignment(Qt.AlignCenter)
        label_severity.setStyleSheet(theme.field_title_style())
        severity_sublayout.addWidget(label_severity)
        severity_combo = QComboBox()
        severity_combo.setView(QListView())
        severity_combo.addItem("Select Code")
        severity_sublayout.addWidget(severity_combo)
        row2_layout.addWidget(severity_subframe)
        
        input_layout.addLayout(row2_layout)
        main_layout.addWidget(input_frame)
        
        # Bottom action buttons
        action_layout = QHBoxLayout()
        action_layout.setSpacing(10)
        
        clear_button = QPushButton("Clear")
        clear_button.setFixedWidth(120)
        clear_button.setStyleSheet(theme.button_style("#dc3545"))
        action_layout.addWidget(clear_button)
        
        copy_code_button = QPushButton("Copy Code")
        copy_code_button.setFixedWidth(120)
        copy_code_button.setStyleSheet(theme.button_style("#28a745"))
        action_layout.addWidget(copy_code_button)
        
        copy_sitrep_button = QPushButton("Copy Report")
        copy_sitrep_button.setFixedWidth(120)
        copy_sitrep_button.setStyleSheet(theme.button_style("#17a2b8"))
        action_layout.addWidget(copy_sitrep_button)
        
        copy_all_button = QPushButton("Copy All")
        copy_all_button.setFixedWidth(120)
        copy_all_button.setStyleSheet(theme.button_style("#007bff"))
        action_layout.addWidget(copy_all_button)
        
        main_layout.addLayout(action_layout)
        
        # Output section
        output_header_layout = QHBoxLayout()
        output_label = QLabel("Brevity Report")
        output_label.setFont(QFont(theme.font_family, 10, QFont.Bold))
        output_label.setStyleSheet(theme.field_title_style())
        output_header_layout.addWidget(output_label)
        
        output_header_layout.addStretch()
        
        narrative_check = QCheckBox("View Detailed Narrative")
        output_header_layout.addWidget(narrative_check)
        
        main_layout.addLayout(output_header_layout)
        
        # Output text area
        output_frame = QFrame()
        output_frame.setFrameStyle(QFrame.Box | QFrame.Plain)
        output_frame_layout = QVBoxLayout(output_frame)
        output_frame_layout.setContentsMargins(0, 0, 0, 0)
        
        output_text = QTextEdit()
        output_text.setMinimumHeight(150)
        output_frame_layout.addWidget(output_text)
        
        main_layout.addWidget(output_frame)
        
        # Narrative section (initially hidden)
        narrative_label = QLabel("Detailed Narrative")
        narrative_label.setFont(QFont(theme.font_family, 10, QFont.Bold))
        narrative_label.setStyleSheet(theme.field_title_style())
        narrative_label.hide()
        main_layout.addWidget(narrative_label)
        
        narrative_frame = QFrame()
        narrative_frame.setFrameStyle(QFrame.Box | QFrame.Plain)
        narrative_frame_layout = QVBoxLayout(narrative_frame)
        narrative_frame_layout.setContentsMargins(0, 0, 0, 0)
        
        narrative_text = QTextEdit()
        narrative_text.setMinimumHeight(200)
        narrative_frame_layout.addWidget(narrative_text)
        
        narrative_frame.hide()
        main_layout.addWidget(narrative_frame)
        
        # Status bar
        status_bar = QStatusBar()
        window.setStatusBar(status_bar)
        
        # Store widgets globally for access by library functions
        gui_widgets = {
            'decode_entry': decode_entry,
            'decode_button': decode_button,
            'list_combo': list_combo,
            'emergency_combo': emergency_combo,
            'status_combo': status_combo,
            'primary_combo': primary_combo,
            'secondary_combo': secondary_combo,
            'severity_combo': severity_combo,
            'clear_button': clear_button,
            'copy_code_button': copy_code_button,
            'copy_sitrep_button': copy_sitrep_button,
            'copy_all_button': copy_all_button,
            'output_text': output_text,
            'narrative_text': narrative_text,
            'narrative_check': narrative_check,
            'narrative_label': narrative_label,
            'narrative_frame': narrative_frame,
            'label_select': label_select,
            'label_emergency': label_emergency,
            'label_status': label_status,
            'label_primary': label_primary,
            'label_secondary': label_secondary,
            'label_severity': label_severity
        }
        
        globals()['gui_widgets'] = gui_widgets
        globals()['status_bar'] = status_bar
        
        # Connect signals
        decode_button.clicked.connect(decode_code)
        decode_entry.returnPressed.connect(decode_code)
        
        clear_button.clicked.connect(clear_fields)
        copy_code_button.clicked.connect(copy_code_text)
        copy_sitrep_button.clicked.connect(copy_sitrep)
        copy_all_button.clicked.connect(copy_all)
        
        narrative_check.stateChanged.connect(toggle_narrative)
        
        def update_combo_bg(combo, text):
            # Only update the style if the text actually changed to a valid/invalid state
            # to avoid redundant layout passes.
            is_neutral = not text or text.startswith("Select ") or text.startswith("No ")
            
            combo.blockSignals(True)  # Safety lock to protect cascading logic
            if is_neutral:
                # Revert to base structural style (inherits system arrow)
                combo.setStyleSheet("")
            else:
                # Apply selection color while preserving the system arrow
                combo.setStyleSheet("background-color: #28a745; color: white; font-weight: bold;")
            combo.blockSignals(False)  # Release lock

        # Connect combo box signals
        list_combo.currentTextChanged.connect(lambda text: handle_menu_select("list", text) if text != "Select Emergency List" else None)
        emergency_combo.currentTextChanged.connect(lambda text: handle_menu_select("emergency", text))
        status_combo.currentTextChanged.connect(lambda text: handle_menu_select("status", text))
        primary_combo.currentTextChanged.connect(lambda text: handle_menu_select("primary", text))
        secondary_combo.currentTextChanged.connect(lambda text: handle_menu_select("secondary", text))
        severity_combo.currentTextChanged.connect(lambda text: handle_menu_select("severity", text))

        for combo in [list_combo, emergency_combo, status_combo, primary_combo, secondary_combo, severity_combo]:
            combo.currentTextChanged.connect(lambda text, c=combo: update_combo_bg(c, text))
            update_combo_bg(combo, combo.currentText())
        
        # Context menu for paste
        decode_entry.setContextMenuPolicy(Qt.CustomContextMenu)
        decode_entry.customContextMenuRequested.connect(lambda pos: paste_into_decode())
        
        # Load JSON files and populate list combo
        emergency_list_mapping = get_json_files()
        list_combo.blockSignals(True)
        for list_id, filename in sorted(emergency_list_mapping.items()):
            list_combo.addItem(filename)
        list_combo.blockSignals(False)
        
        # Load first file if available
        if emergency_list_mapping:
            first_list_id = sorted(emergency_list_mapping.keys())[0]
            load_selected_file(first_list_id)
            list_combo.setCurrentText(emergency_list_mapping[first_list_id])
        else:
            show_status_message("No valid JSON files found", 10000)
            logging.warning("No valid JSON files found")
        
        window.show()
        sys.exit(app.exec_())
    except Exception as e:
        logging.error(f"Exception in main: {str(e)}")
        traceback.print_exc()
