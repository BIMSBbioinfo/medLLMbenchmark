## PREPROCESSING MIMIC_IV

## import libraries
import pandas as pd
import numpy as np
from io import StringIO
from tqdm import tqdm
import re

## Import datasets from MIMIC-IV, MIMIC-IV-ED, MIMIC-IV-Note
## Load from MIMIC-IV-ED
triage = pd.read_csv("/mimic-iv-ed-2.2/ed/triage.csv", on_bad_lines='skip', low_memory=False)
vitalsigns = pd.read_csv("/mimic-iv-ed-2.2/ed/vitalsign.csv", on_bad_lines='skip', low_memory=False)
ed_stays = pd.read_csv("/mimic-iv-ed-2.2/ed/edstays.csv")
diagnostics = pd.read_csv('/mimic-iv-ed-2.2/ed/diagnosis.csv',on_bad_lines='skip')


## Load from MIMIC-IV
patients = pd.read_csv("/mimic-iv/mimic-iv-3.0/hosp/patients.csv.gz", compression='gzip', low_memory=False)


## Load Discharge from MIMIC-IV-Note
# Read the discharge.csv file into a string
txt = open('/mimic-iv-note/discharge.csv').read()

# Replace all occurrences of '|' with ',<vl>' (custom delimiter), ',""""\n' with ',<br>' (indicating a line break marker), 'Followup Instructions:\n___\n""""' with new markers '</br>|' for parsing
txt = txt.replace('|', ',<vl>')
txt = txt.replace(',""""\n', ',<br>')
txt = txt.replace('Followup Instructions:\n___\n""""','Followup Instructions:\n___\n</br>|')

# find text between <br> and </br> and replace any ',' with '<comma>'
txt = re.sub(r'<br>([^<]*)</br>', lambda x: x.group(0).replace(',', '<comma>'), txt)

# Remove all occurrences of double quotes '"' from the text
txt = txt.replace('"', '')

# Replace the 'text\n' pattern with 'text|' to format for CSV parsing
txt = txt.replace('text\n', 'text|')

# Use pandas to read the modified txt content as a CSV, using '|' as the line terminator
df = pd.read_csv(StringIO(txt), lineterminator='|', on_bad_lines='warn')


## merge different datasets
## Add "stay_id" and "text" from edstays dataset
for index, row in df.iterrows():
    try:
        hadm_id = float(row['hadm_id'])
        # Find the corresponding 'stay_id' in 'ed_stays' DataFrame that matches the 'hadm_id'
        stay_id = ed_stays[ed_stays['hadm_id'] == hadm_id]['stay_id']

        # If no matching 'stay_id' is found, skip to the next iteration
        if stay_id.empty:
            continue

        df.at[index, 'stay_id'] = stay_id.iloc[0]
        
    except Exception as e:
        print(f"{e} at {index}")
        continue

df = df[df['stay_id'].notnull()]


## Add all columns from Triage dataset
# merged to the triage df, because it is unique on stay_id
df = pd.merge(triage, df, on="stay_id", how="inner")

## Add gender and race from edstays dataset
df = pd.merge(df, ed_stays, on='stay_id')

# Removing Duplicate Rows Based on subject_id
unique_df = df.drop_duplicates(subset=['subject_id_x'])


## Add age from patient dataset
unique_df = pd.merge(unique_df, patients, on='subject_id')


## Extract Relevant Information from the Clinical Text
## EXTRACT: Tests
def get_tests(text):
    lower_text = text.lower()
    try:
        if "discharge labs" in lower_text.split("pertinent results:")[1].split('brief hospital course:')[0]:
            return lower_text.split("pertinent results:")[1].split('brief hospital course:')[0].split('discharge labs')[0]
        else:
            return lower_text.split("pertinent results:")[1].split('brief hospital course:')[0]
    except:
        #print(lower_text)
        return None

unique_df["tests"] = unique_df['text'].apply(get_tests)


## EXTRACT: Past medication
def get_medication(text):
    lower_text = text.lower()
    try:
        # Extract the text between "medications on admission:" and "discharge medications:"
        return lower_text.split("medications on admission:")[1].split('discharge medications:')[0]
    except:
        # print(lower_text)
        return None

unique_df["medication"] = unique_df['text'].apply(get_medication)


## EXTRACT: History of Present Illness (to be continued and refined later on in the code)
def get_HPI(text):
    # Replace custom placeholders with their intended characters and clean up text markers
    text = text.replace('<comma>', ',').replace('<br>', '').replace('</br>', '')
    
    # Extract the text between "History of Present Illness:" and "Physical Exam:" sections
    text = text.split('History of Present Illness:')[-1].split('Physical Exam:')[0]
    return text

unique_df['preprocessed_text'] = unique_df['text'].apply(get_HPI)


## Cleaning and organizing the Dataframe for clarity
## Drop Redundant Columns and Rename Relevant Columns for Consistency and Clarity
unique_df = unique_df.drop(columns=['subject_id_x', 'subject_id_y', 'hadm_id_x', 'gender_y'])
unique_df = unique_df.rename(columns={
    'hadm_id_y': 'hadm_id',
    'gender_x': 'gender'
})
df = unique_df.copy()


## Merge ICD information from diagnostics dataset
# Filter the diagnostics data to keep only rows where "seq_num" equals 1 (indicating the most relevant ICD code)
diagnostics = diagnostics[diagnostics["seq_num"] == 1]

# Merge diagnostics data into df to add 'icd_code', 'icd_title', and 'icd_version' columns
df = df.merge(diagnostics[['stay_id', 'icd_code', 'icd_title', "icd_version"]],
              on='stay_id', how='left')

# Remove rows where 'icd_code' is NaN
df = df.dropna(subset=['icd_code'])

# Drop columns that are no longer needed for the analysis or further processing
df = df.drop(columns=["note_id", "note_type", "note_seq", "charttime", "storetime", "intime", "outtime", "arrival_transport", "disposition", "anchor_year", "anchor_year_group", "dod" ])

## Create Initial Vitals from Temperature, Heartrate, respiration rate, o2 saturation, bloodpressure (dbp, sbp)
def create_vitals(row):
    vitals = []
    
    if not pd.isna(row['temperature']):
        vitals.append(f"Temperature: {row['temperature']}")
    if not pd.isna(row['heartrate']):
        vitals.append(f"Heartrate: {row['heartrate']}")
    if not pd.isna(row['resprate']):
        vitals.append(f"resprate: {row['resprate']}")
    if not pd.isna(row['o2sat']):
        vitals.append(f"o2sat: {row['o2sat']}")
    if not pd.isna(row['sbp']):
        vitals.append(f"sbp: {row['sbp']}")   
    if not pd.isna(row['dbp']):
        vitals.append(f"dbp: {row['dbp']}") 
    
    return ", ".join(vitals)

df.loc[:,'initial_vitals'] = df.apply(create_vitals, axis=1)


## Create Patient Info from Gender, Race and Year
def create_patient_info(row):
    patient_info = []
    
   # Append the gender information with a readable format
    if row["gender"] == "F":
        patient_info.append("Gender: Female")
    elif row["gender"] == "M":
        patient_info.append("Gender: Male")
    else:
        patient_info.append(f"Gender: {row['gender']}")

    patient_info.append(f"Race: {row['race']}")
    patient_info.append(f"Age: {row['anchor_age']}")
    
    return ", ".join(patient_info)

df.loc[:,'patient_info'] = df.apply(create_patient_info, axis=1)


## Cleaning and organizing the Dataframe for clarity
# Drop columns that are no longer needed for the analysis or further processing and rearrange columns
df = df.drop(columns=["gender", "race", "anchor_age", "temperature", "heartrate", "resprate", "o2sat", "sbp", "dbp"])

df = df[['stay_id', 'subject_id', 'hadm_id', "text", 'patient_info', 'initial_vitals', 'pain', 'chiefcomplaint', 'preprocessed_text', 'medication', 'tests', 'acuity', 'icd_code', 'icd_title', 'icd_version']]


## remove rows that have nans in acuity, because acuity will be predicted and NaNs carry no useful information
df = df.dropna(subset=['acuity'])
df = df.dropna(subset=['tests'])


## convert nans to empty strings
df["pain"] = df['pain'].fillna("")
df["chiefcomplaint"] = df['chiefcomplaint'].fillna("")
df["medication"] = df['medication'].fillna("")


## convert numpy.float64 to numpy.int64
df['acuity'] = df['acuity'].astype(np.int64)
df['hadm_id'] = df['hadm_id'].astype(np.int64)
df['icd_version'] = df['icd_version'].astype(np.int64)

## rename acuity to triage
df = df.rename(columns={"acuity": "triage"})


## find the rows that have "history of present illness" in the "text" column and keep only these rows
hpi = df['text'].str.contains('history of present illness', case=False, na=False)
hpi_index = hpi[hpi==True].index
df = df.loc[hpi_index]


## EXTRACT: HPI
def extract_hpi(text):
    pos_past_med_hist = text.lower().find('past medical history:')
    pos_soc_hist = text.lower().find('social history:')
    pos_fam_hist = text.lower().find('family history:')
    #text = text.replace("\n", " ")
    if pos_past_med_hist != -1:
        return text[:pos_past_med_hist].strip()
    elif pos_soc_hist != -1:
        return text[:pos_soc_hist].strip()
    elif pos_soc_hist != -1:
        return text[:pos_fam_hist].strip()
    else:
        return text

df["HPI"] = df["preprocessed_text"].apply(extract_hpi)


## EXTRACT: DIAGNOSIS
def extract_diagnosis(text):
    split_text = text.split("Discharge Diagnosis:" )[-1].split("Discharge Condition:")[0]
    split_text= split_text.replace('<comma>', ', ')
    return("Discharge Diagnosis: " + split_text)

df["diagnosis"] = df["text"].apply(extract_diagnosis)


## PROCESS HPI
## cut length of HPI <2000 and the tests <3000
string_lengths = df['HPI'].str.len()
mask = string_lengths<2000
df = df[mask]

string_lengths = df['HPI'].str.len()
mask = string_lengths>50
df = df[mask]

string_lengths = df['tests'].str.len()
mask = string_lengths<3000
df = df[mask]


## Removing Unwanted Sections Related to ED Course and Initial Vitals
df = df.dropna(subset=['HPI'])
df = df[df['HPI'] != ""]


## HPI preprocess
def extract_only_hpi(text):

    ## remove everything after
    #text = re.sub(re.compile("in the ED.*", re.IGNORECASE), "", text)
    text = re.sub(re.compile(r"in the ED, initial vital.*", re.IGNORECASE | re.DOTALL), "", text)
    text = re.sub(re.compile(r"in the ED initial vital.*", re.IGNORECASE | re.DOTALL), "", text)
    text = re.sub(re.compile(r"\bED Course.*", re.IGNORECASE | re.DOTALL), "", text)
    text = re.sub(re.compile(r"\bIn ED initial VS.*", re.IGNORECASE | re.DOTALL), "", text)
    text = re.sub(re.compile(r"in the ED, initial VS.*", re.IGNORECASE | re.DOTALL), "", text)
    text = re.sub(re.compile(r"\binitial VS.*", re.IGNORECASE | re.DOTALL), "", text)
    text = re.sub(re.compile(r"in the ED.*", re.IGNORECASE | re.DOTALL), "", text)

    return text

tqdm.pandas()
df["HPI"] = df["HPI"].progress_apply(extract_only_hpi)


## Remove the ones that have ED in them
mask = df["HPI"].str.contains(r'\bED', case=False, na=False)
df = df[~mask]


## remove where test is nan to be able to compare between normal user and expert
df = df.dropna(subset=['tests'])


## PROCESS DIAGNOSIS
## Removing Specific Headers, Unwanted Secrtions, and irrelevant Records
## remove the header "discharge diagnosis"
def remove_header(text, header):
    text = re.sub(re.compile(header, re.IGNORECASE), "", text)
    return text


## Remove Header in diagnosis "discharge diagnosis"
df['diagnosis'] = df['diagnosis'].apply(lambda text: remove_header(text, "discharge diagnosis:"))


## Remove all content before and including the "Facility:\n___" marker
def delete_before_string(text):
    text = re.sub(re.compile(r".*Facility:\n___", re.IGNORECASE | re.DOTALL), "", text)
    return text
df['diagnosis'] = df['diagnosis'].apply(delete_before_string)


## Remove all content before and including the "___ Diagnosis:" marker
def delete_before_string(text):
    text = re.sub(re.compile(r".*___ Diagnosis:", re.IGNORECASE | re.DOTALL), "", text)
    return text
df['diagnosis'] = df['diagnosis'].apply(delete_before_string)


## Remove all content after the "PMH" marker (Past Medical History)
def delete_after_string(text):
    text = re.sub(re.compile(r"PMH.*", re.IGNORECASE | re.DOTALL), "", text)
    return text
df['diagnosis'] = df['diagnosis'].apply(delete_after_string)


## FILTER ROWS with excessive Information to preserve prediction integrity
# Filter out rows in 'HPI' that contain specific terms like 'ER', 'Emergency room', 'Emergency department', or 'impression'
# These rows likely refer to emergency settings and shouldn't be in the text for further analysis
mask = df["HPI"].str.contains(' ER ', case=False, na=False)
df = df[~mask]
mask = df["HPI"].str.contains('Emergency room', case=False, na=False)
df = df[~mask]
mask = df["HPI"].str.contains('Emergency department', case=False, na=False)
df = df[~mask]
mask = df["HPI"].str.contains('impression', case=False, na=False)
df = df[~mask]

# Filter out rows in 'diagnosis' that contain the terms 'deceased' or 'died'
mask = df["diagnosis"].str.contains('deceased', case=False, na=False)
df = df[~mask]
mask = df["diagnosis"].str.contains('died', case=False, na=False)
df = df[~mask]

# Further filter out rows where 'diagnosis' contains the term 'history of present illness'
# This ensures that diagnosis-related fields don't inadvertently contain HPI-related content
mask_hpi = df["diagnosis"].str.contains('history of present illness', case=False, na=False)
df = df[~mask_hpi]
print(len(df))


## CREATE PRIMARY AND SECONDARY DIAGNOSIS
## Drop rows that include "primary" as primary diagnosis but not surely in the beginning
mask = df["diagnosis"].str.contains('primary', case=False, na=False)
ind = df[mask].index.tolist()
mask2 = df['diagnosis'].str.contains(r'^\s*\nprimary', flags=re.IGNORECASE, regex=True)
ind2 = df[mask2].index.tolist()
ind_drop = set(ind) - set(ind2)
df = df[~df.index.isin(ind_drop)]


## Drop rows that include "secondary" as secondary diagnosis but not surely in the beginning
mask = df["diagnosis"].str.contains('secondary', case=False, na=False)
ind = df[mask].index.tolist()
mask2 = df['diagnosis'].str.contains('\nsecondary', flags=re.IGNORECASE, regex=True)
ind2 = df[mask2].index.tolist()
ind_drop = set(ind) - set(ind2)
df = df[~df.index.isin(ind_drop)]


## Segregate Discharge Diagnosis into Primary and Secondary Categories with Post-Processing and Filtering 
df["primary_diagnosis"] = None
df["secondary_diagnosis"] = None
## divide discharge diagnosis into primary and secondary diangosis if possible
for i in df.index:
    index = df["diagnosis"][i].lower().find('secondary')
    if index != -1:
        df.loc[i, "primary_diagnosis"] = df["diagnosis"][i][:index]
        df.loc[i, "secondary_diagnosis"] = df["diagnosis"][i][index:]
    else:
        df.loc[i, "primary_diagnosis"] = df["diagnosis"][i]
        df.loc[i, "secondary_diagnosis"] = ""


## Remove any text after "___ Condition:" 
def delete_after_string(text):
    text = re.sub(re.compile(r"___ Condition:.*", re.IGNORECASE | re.DOTALL), "", text)
    return text
df['primary_diagnosis'] = df['primary_diagnosis'].apply(delete_after_string)


## Filter rows in the DataFrame where 'primary_diagnosis' has fewer than 16 single newlines (less than 16 diagnoses)
def count_single_newlines(text):
    single_newlines = re.findall(r'(?<!\n)\n(?!\n)', text)
    return len(single_newlines)

# Apply the function to the entire column and get a list of counts
newline_counts = df['primary_diagnosis'].apply(count_single_newlines).tolist()

mask = [value < 16 for value in newline_counts]
df = df[mask]

df = df.drop(columns=['text', 'preprocessed_text', 'medication'], inplace=False)


## convert primary and secondary diagnoses into a list of diagnoses for each patient
## replace colon without \n to colon with \n
def colon_replacement(text):

    # remove everything after
    text = re.sub(r":\s*(?!\n)", ':\n', text)

    return text

df['primary_diagnosis'] = df['primary_diagnosis'].apply(colon_replacement)
df['secondary_diagnosis'] = df['secondary_diagnosis'].apply(colon_replacement)


## make diagnosis into a list for each row
liste = df['primary_diagnosis'].apply(lambda x: [s for s in x.split('\n') if s.strip()] if pd.notna(x) else x)
liste = liste.apply(lambda lst: [item for item in lst if "primary diagnoses" not in item.lower()])
liste = liste.apply(lambda lst: [item for item in lst if "primary diagnosis" not in item.lower()])
liste = liste.apply(lambda lst: [item for item in lst if "primary" not in item.lower()]) 
liste = liste.apply(lambda lst: [item for item in lst if "====" not in item.lower()])
liste = liste.apply(lambda lst: [item for item in lst if "" != item.lower()])

def remove_number_prefix(item):
    return re.sub(r'^[1-8]\)\s*', '', item)
liste = liste.apply(lambda lst: [remove_number_prefix(item) for item in lst])

df["primary_diagnosis"] = liste


df['secondary_diagnosis'] = df['secondary_diagnosis'].fillna("")
liste = df['secondary_diagnosis'].apply(lambda x: [s for s in x.split('\n') if s.strip()])

liste = liste.apply(lambda lst: [item for item in lst if "secondary diagnoses" not in item.lower()])
liste = liste.apply(lambda lst: [item for item in lst if "secondary diagnosis" not in item.lower()])
liste = liste.apply(lambda lst: [item for item in lst if "secondary" not in item.lower()]) 
liste = liste.apply(lambda lst: [item for item in lst if "====" not in item.lower()])
liste = liste.apply(lambda lst: [item for item in lst if "" != item.lower()])

def remove_number_prefix(item):
    return re.sub(r'^[1-8]\)\s*', '', item)
liste = liste.apply(lambda lst: [remove_number_prefix(item) for item in lst])

df["secondary_diagnosis"] = liste

## Extract the first 2200 (goal is to predict 2000, 200 are in case rows need to be remove - see postprocessing and additional postprocessing)
df = df[:2200]


## save file
df.to_csv('MIMIC-IV-Ext-Triage-Specialty-Diagnosis-Decision-Support.csv', index=False)
