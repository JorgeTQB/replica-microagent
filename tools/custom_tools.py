import os
import json
import sys
import math
from collections import defaultdict
from typing import Type, Any, List
from pydantic import BaseModel, Field
from microagent_shim import BaseTool
import glob
from sentence_transformers import SentenceTransformer
from sklearn.metrics.pairwise import cosine_similarity
import numpy as np
import re
import difflib
from sklearn.feature_extraction.text import TfidfVectorizer

from microagent_shim import APP_CONFIG, WORKING_DIR

# Define valid relationship types as a global constant
VALID_RELATIONSHIP_TYPES = [
    "EXTENDS",           
    "IMPLEMENTS",        
    "CALLS",             
    "USES",              
    "REFERENCES",        
    "INJECTS",           
    "ASSOCIATES",        
    "ANNOTATED_WITH",    
    "CREATES",           
    "PERSISTS",          
    "DEPENDS_ON"         
]

VALID_INVERTED_RELATIONSHIP_TYPES = [
    "EXTENDED_BY",
    "IMPLEMENTED_BY",
    "CALLED_BY",
    "USED_BY",
    "REFERENCED_BY",
    "INJECTED_BY",
    "ASSOCIATED_WITH",
    "ANNOTATES",
    "CREATED_BY",
    "PERSISTED_BY",
    "DEPENDENCY_OF"
]

def clean_path(path_str: str) -> str:
    """Helper function to clean path strings by removing surrounding quotes, trailing quotes, and whitespace."""
    if isinstance(path_str, str):
        path_str = path_str.strip()
        if (path_str.startswith('"') and path_str.endswith('"')) or \
                (path_str.startswith("'") and path_str.endswith("'")):
            path_str = path_str[1:-1]
        elif path_str.endswith('"') or path_str.endswith("'"):
            path_str = path_str[:-1]
        elif path_str.startswith('"') or path_str.startswith("'"):
            path_str = path_str[1:]
        path_str = path_str.strip()
    return path_str


def _generate_directory_tree(root_dir, max_depth=4, indent="  ", prefix="", is_last=True, ignore_dirs=None):
    """Generate a tree representation of the directory structure."""
    if ignore_dirs is None:
        ignore_dirs = ['.git', '__pycache__', 'target', 'node_modules', '.mvn', '.github', '.devcontainer']

    if max_depth < 0:
        return prefix + "..."

    basename = os.path.basename(root_dir)

    if basename in ignore_dirs:
        return ""

    result = []

    connector = "└── " if is_last else "├── "
    result.append(prefix + connector + basename + "/")

    child_prefix = prefix + ("    " if is_last else "│   ")

    try:
        items = sorted(os.listdir(root_dir))
        items = [item for item in items if not item.startswith('.') and item not in ignore_dirs]
        dirs = [item for item in items if os.path.isdir(os.path.join(root_dir, item))]
        files = [item for item in items if os.path.isfile(os.path.join(root_dir, item))]

        for i, item in enumerate(dirs):
            item_path = os.path.join(root_dir, item)
            is_last_item = (i == len(dirs) - 1) and not files
            subtree = _generate_directory_tree(item_path, max_depth - 1, indent, child_prefix, is_last_item,
                                               ignore_dirs)
            if subtree:
                result.append(subtree)

        for i, item in enumerate(files):
            is_last_item = i == len(files) - 1
            connector = "└── " if is_last_item else "├── "
            result.append(child_prefix + connector + item)

    except PermissionError:
        result.append(child_prefix + "└── <permission denied>")
    except Exception as e:
        result.append(child_prefix + f"└── <error: {str(e)}>")

    return "\n".join(result)


# --- Tool Implementations ---

class GetSourceCodeInput(BaseModel):
    file_path: str = Field(...,
                           description="The path to the file to read. Do not include quotes and avoid whitespace or newlines. Example: resources/app_name/src/main/java/org/example/MyClass.java")


class GetSourceCode(BaseTool):
    name: str = "read_file"
    description: str = "Read the source code of a java class. Examine specific files for detailed information, e.g. verify class roles and functionalities."
    args_schema: Type[BaseModel] = GetSourceCodeInput

    def _run(self, file_path: str) -> str:
        try:
            file_path = clean_path(file_path)
            app_name = APP_CONFIG["app_name"]

            if not os.path.isabs(file_path):
                full_path = os.path.join(WORKING_DIR, file_path)
                if not os.path.exists(full_path):
                    resource_path = os.path.join(WORKING_DIR, "resources", app_name, file_path)
                    if os.path.exists(resource_path):
                        full_path = resource_path
                file_path = full_path

            if not os.path.exists(file_path):
                return f"Error: File '{file_path}' does not exist. Please check if the path is correct and try again."
            if not os.path.isfile(file_path):
                return f"Error: '{file_path}' is not a file. Please provide a valid file path."

            with open(file_path, 'r', encoding='utf-8', errors='replace') as f:
                return f.read()
        except Exception as e:
            return f"Error reading file: {str(e)}"


class ListDirectoryInput(BaseModel):
    directory_path: str = Field(...,
                                description="The path to the directory to list. Do not include quotes and avoid whitespace or newlines. Example: resources/app_name/src/main/java/org/example")


class ListDirectory(BaseTool):
    name: str = "list_directory"
    description: str = "List the contents of a directory. You can explore directories and discover files, e.g. find domain packages."
    args_schema: Type[BaseModel] = ListDirectoryInput

    def _run(self, directory_path: str) -> str:
        try:
            directory_path = clean_path(directory_path)
            app_name = APP_CONFIG["app_name"]

            if not os.path.isabs(directory_path):
                full_path = os.path.join(WORKING_DIR, directory_path)
                if not os.path.exists(full_path):
                    resource_path = os.path.join(WORKING_DIR, "resources", app_name, directory_path)
                    if os.path.exists(resource_path):
                        full_path = resource_path
                directory_path = full_path

            if not os.path.exists(directory_path):
                return f"Error: Directory '{directory_path}' does not exist. Please check if the path is correct and try again."
            if not os.path.isdir(directory_path):
                return f"Error: '{directory_path}' is not a directory. Please provide a valid directory path."

            items = os.listdir(directory_path)
            result = [f"Contents of {directory_path}:"]
            directories, files = [], []

            for item in sorted(items):
                item_path = os.path.join(directory_path, item)
                if os.path.isdir(item_path):
                    directories.append(f"📁 {item}/")
                else:
                    size = os.path.getsize(item_path)
                    size_str = f"{size} bytes"
                    if size > 1024 * 1024:
                        size_str = f"{size / (1024 * 1024):.1f} MB"
                    elif size > 1024:
                        size_str = f"{size / 1024:.1f} KB"
                    files.append(f"📄 {item} ({size_str})")

            result.extend(directories)
            result.extend(files)
            return "\n".join(result)
        except Exception as e:
            return f"Error listing directory: {str(e)}"


class SearchDirectoryInput(BaseModel):
    path: str = Field(...,
                      description="The path to the directory to search. Example: resources/app_name/src/main/java/org/example")
    term: str = Field(..., description="The term to search for in files.")
    file_pattern: str = Field("*", description="Optional glob pattern to filter files to search.")


class SearchDirectory(BaseTool):
    name: str = "search_directory"
    description: str = "Search for files in a directory that contain a specific term in their content or filename (case-insensitive). You can find files in a directory containing specific content."
    args_schema: Type[BaseModel] = SearchDirectoryInput

    def _run(self, path: str, term: str, file_pattern: str = "*") -> str:
        try:
            directory_path = clean_path(path)
            app_name = APP_CONFIG["app_name"]

            if not os.path.isabs(directory_path):
                full_path = os.path.join(WORKING_DIR, directory_path)
                if not os.path.exists(full_path):
                    resource_path = os.path.join(WORKING_DIR, "resources", app_name, directory_path)
                    if os.path.exists(resource_path):
                        full_path = resource_path
                directory_path = full_path

            if not os.path.exists(directory_path): return f"Error: Directory '{directory_path}' does not exist"
            if not os.path.isdir(directory_path): return f"Error: '{directory_path}' is not a directory"

            files = glob.glob(os.path.join(directory_path, file_pattern), recursive=True)
            if not files: return f"No files matching pattern '{file_pattern}' found in {directory_path}"

            filename_matches, content_matches = [], []
            search_term_lower = term.lower()

            for file_path in files:
                if not os.path.isfile(file_path): continue

                if search_term_lower in os.path.basename(file_path).lower():
                    filename_matches.append(file_path)
                try:
                    with open(file_path, 'r', encoding='utf-8', errors='replace') as file:
                        if search_term_lower in file.read().lower():
                            content_matches.append(file_path)
                except Exception:
                    continue

            all_matches = sorted(list(set(filename_matches + content_matches)))
            if not all_matches: return f"No files containing '{term}' found in {directory_path}"

            result = [f"Found {len(all_matches)} files containing '{term}':"]
            result.extend([f"  - {match}" for match in all_matches])
            return "\n".join(result)
        except Exception as e:
            return f"Error searching directory: {str(e)}"


class SearchFileInput(BaseModel):
    path: str = Field(...,
                      description="The path to the file to search. Example: resources/app_name/src/main/java/org/example/MyClass.java")
    term: str = Field(..., description="The term to search for in the file.")


class SearchFile(BaseTool):
    name: str = "search_file"
    description: str = "Search for a term in a file and return matching lines (case-insensitive). You can find specific content within files, e.g. find references to certain objects."
    args_schema: Type[BaseModel] = SearchFileInput

    def _run(self, path: str, term: str) -> str:
        try:
            file_path = clean_path(path)
            app_name = APP_CONFIG["app_name"]

            if not os.path.isabs(file_path):
                full_path = os.path.join(WORKING_DIR, file_path)
                if not os.path.exists(full_path):
                    resource_path = os.path.join(WORKING_DIR, "resources", app_name, file_path)
                    if os.path.exists(resource_path):
                        full_path = resource_path
                file_path = full_path

            if not os.path.exists(file_path): return f"Error: File '{file_path}' does not exist"
            if not os.path.isfile(file_path): return f"Error: '{file_path}' is not a file"

            with open(file_path, 'r', encoding='utf-8', errors='replace') as file:
                lines = file.readlines()

            matches = [f"Line {i + 1}: {line.strip()}" for i, line in enumerate(lines) if term.lower() in line.lower()]

            if matches: return "\n".join(matches)
            return f"No matches found for '{term}' in {file_path}"
        except Exception as e:
            return f"Error searching file: {str(e)}"


class GetFileInfoInput(BaseModel):
    file_path: str = Field(...,
                           description="The path to the file to get information about. Example: resources/app_name/src/main/java/org/example/MyClass.java")


class GetFileInfo(BaseTool):
    name: str = "get_file_info"
    description: str = "Get detailed information about a file, such as size, path, and line count."
    args_schema: Type[BaseModel] = GetFileInfoInput

    def _run(self, file_path: str) -> str:
        try:
            file_path = clean_path(file_path)
            if not os.path.isabs(file_path): file_path = os.path.join(WORKING_DIR, file_path)
            if not os.path.exists(file_path): return f"File {file_path} does not exist"

            info = {
                "exists": os.path.exists(file_path),
                "size": os.path.getsize(file_path),
                "is_file": os.path.isfile(file_path),
                "is_dir": os.path.isdir(file_path),
                "abs_path": os.path.abspath(file_path)
            }
            if info["is_file"]:
                try:
                    with open(file_path, 'r', encoding='utf-8', errors='replace') as f:
                        info["line_count"] = sum(1 for _ in f)
                except:
                    info["line_count"] = "Cannot determine (possibly binary file)"
            return json.dumps(info, indent=2)
        except Exception as e:
            return f"Error getting file info: {str(e)}"


class GetClassSummaryInput(BaseModel):
    class_name: str = Field(...,
                            description="The full name of the class (including package) to get information about. Example: org.springframework.samples.petclinic.model.Pet")


class GetClassSummary(BaseTool):
    name: str = "get_class_summary"
    description: str = "Get the summary of a class by its full name (package_name.class_name) from the class_summaries.json file."
    args_schema: Type[BaseModel] = GetClassSummaryInput

    def _run(self, class_name: str) -> str:
        try:
            app_name = APP_CONFIG["app_name"]
            context_dir = os.path.join(WORKING_DIR, "context", app_name)
            class_summaries_file = os.path.join(context_dir, "class_summaries.json")

            if not os.path.exists(
                class_summaries_file): return f"Error: Class summaries file not found at {class_summaries_file}"

            with open(class_summaries_file, 'r', encoding='utf-8', errors='replace') as f:
                class_summaries = json.load(f)

            if class_name in class_summaries:
                class_data = class_summaries[class_name]
                summary = class_data.get("summary", "No summary available")
                file_path = class_data.get("file_path", "No file path available")
                return f"Class: {class_name}\nSummary: {summary}\nFile Path: {file_path}"
            return f"Class '{class_name}' not found in class summaries"
        except Exception as e:
            return f"Error getting class summary: {str(e)}"


class GetClassBasicInfoInput(BaseModel):
    class_name: str = Field(...,
                            description="The full name of the class (including package) to get information about. Example: org.springframework.samples.petclinic.model.Pet")


class GetClassBasicInfo(BaseTool):
    name: str = "get_class_basic_info"
    description: str = "Get the complete info (imports, annotations, methods, fields, relationships) of a class by its full name (package_name.class_name) from the class_info_dependency.json file. The number of the relationship with certain class indicates the total occurances of this relationship. Note that the class dependency graph may not be accurate."
    args_schema: Type[BaseModel] = GetClassBasicInfoInput

    def _run(self, class_name: str) -> str:
        try:
            app_name = APP_CONFIG["app_name"]
            context_dir = os.path.join(WORKING_DIR, "context", app_name)
            class_info_file = os.path.join(context_dir, "class_info_dependency.json")

            if not os.path.exists(class_info_file): return f"Error: Class info file not found at {class_info_file}"

            with open(class_info_file, 'r', encoding='utf-8', errors='replace') as f:
                class_info = json.load(f)

            if class_name not in class_info: return f"Class '{class_name}' not found in class info"

            class_data = class_info[class_name]
            result = [f"Class: {class_name}"]
            if class_data.get("imports"): result.extend(
                ["\nImports:"] + [f"  - {imp}" for imp in class_data["imports"]])
            if class_data.get("annotations"): result.extend(
                ["\nAnnotations:"] + [f"  - {anno}" for anno in class_data["annotations"]])
            if class_data.get("methods"): result.extend(
                ["\nMethods:"] + [f"  - {m.get('signature', 'N/A')}" for m in class_data["methods"]])
            if class_data.get("fields"): result.extend(
                ["\nFields:"] + [f"  - {f.get('declaration', 'N/A')}" for f in class_data["fields"]])
            if class_data.get("relationships"):
                result.append("\nRelationships:")
                for rel_type, targets in class_data["relationships"].items():
                    result.append(f"  {rel_type}:")
                    result.extend([f"    - {target}" for target in targets])

            return "\n".join(result)
        except Exception as e:
            return f"Error getting class info: {str(e)}"


class GetClassRelationshipInput(BaseModel):
    class_name: str = Field(...,
                            description="The full name of the class (including package) to get info about. Example: org.springframework.samples.petclinic.model.Pet")


class GetClassRelationship(BaseTool):
    name: str = "get_class_relationship"
    description: str = "Get only the relationships of a class by its full name from the class_info_dependency.json file."
    args_schema: Type[BaseModel] = GetClassRelationshipInput

    def _run(self, class_name: str) -> str:
        try:
            app_name = APP_CONFIG["app_name"]
            context_dir = os.path.join(WORKING_DIR, "context", app_name)
            class_info_file = os.path.join(context_dir, "class_info_dependency.json")

            if not os.path.exists(class_info_file): return f"Error: Class info file not found at {class_info_file}"

            with open(class_info_file, 'r', encoding='utf-8') as f:
                class_info = json.load(f)

            if class_name not in class_info: return f"Class '{class_name}' not found"

            class_data = class_info[class_name]
            if not class_data.get("relationships"): return f"No relationships found for class '{class_name}'"

            result = [f"Relationships for {class_name}:"]
            for rel_type, targets in class_data["relationships"].items():
                result.append(f"\n{rel_type}:")
                result.extend([f"  - {target}" for target in targets])
            return "\n".join(result)
        except Exception as e:
            return f"Error getting class relationships: {str(e)}"


class SearchClassInfoInput(BaseModel):
    search_term: str = Field(..., description="The term to search for in class names. Example: Controller")


class SearchClassInfo(BaseTool):
    name: str = "search_class_info"
    description: str = "Search for classes by a partial name or pattern in the class_info_dependency.json file."
    args_schema: Type[BaseModel] = SearchClassInfoInput

    def _run(self, search_term: str) -> str:
        try:
            app_name = APP_CONFIG["app_name"]
            context_dir = os.path.join(WORKING_DIR, "context", app_name)
            class_info_file = os.path.join(context_dir, "class_info_dependency.json")

            if not os.path.exists(class_info_file): return f"Error: Class info file not found at {class_info_file}"

            with open(class_info_file, 'r', encoding='utf-8') as f:
                class_info = json.load(f)

            matches = [name for name in class_info if search_term.lower() in name.lower()]

            if not matches: return f"No classes found matching '{search_term}'"

            result = [f"Found {len(matches)} classes matching '{search_term}':"]
            result.extend([f"- {match}" for match in sorted(matches)])
            return "\n".join(result)
        except Exception as e:
            return f"Error searching class info: {str(e)}"


class NoArgsToolInput(BaseModel):
    """No arguments needed for this tool."""
    pass


class GetAllClassSummaries(BaseTool):
    name: str = "get_all_class_summaries"
    description: str = "Get all class summaries from the class_summaries.json file. Provides a high-level overview of all classes."
    args_schema: Type[BaseModel] = NoArgsToolInput

    def _run(self) -> str:
        try:
            app_name = APP_CONFIG["app_name"]
            context_dir = os.path.join(WORKING_DIR, "context", app_name)
            summaries_file = os.path.join(context_dir, "class_summaries.json")

            if not os.path.exists(summaries_file): return f"Error: Class summaries file not found at {summaries_file}"

            with open(summaries_file, 'r', encoding='utf-8') as f:
                summaries = json.load(f)

            result = ["Class Summaries:"]
            for name, data in sorted(summaries.items()):
                summary = data.get("summary", "No summary available")
                result.append(f"\n- {name}: {summary}")
            return "\n".join(result)
        except Exception as e:
            return f"Error getting all class summaries: {str(e)}"


class GetDatabaseSummary(BaseTool):
    name: str = "get_database_summary"
    description: str = "Get the database schema/script summarization to understand data relationships. No input parameters required."
    args_schema: Type[BaseModel] = NoArgsToolInput

    def _run(self) -> str:
        try:
            app_name = APP_CONFIG["app_name"]
            database_dir = os.path.join(WORKING_DIR, "database", app_name)
            database_pattern = os.path.join(database_dir, "*-summary.json")
            
            # Use glob to find all matching files
            database_files = glob.glob(database_pattern)
            
            if not database_files:
                return f"No database summary files found matching pattern: {database_pattern}"
            
            # Read all matching database summary files
            summaries = []
            for db_file in sorted(database_files):
                try:
                    with open(db_file, 'r', encoding='utf-8') as f:
                        file_name = os.path.basename(db_file)
                        content = f.read()
                        summaries.append(f"=== {file_name} ===\n{content}")
                except Exception as e:
                    summaries.append(f"=== {os.path.basename(db_file)} ===\nError reading file: {str(e)}")
            
            return f"Database Summary:\n\n" + "\n\n".join(summaries)
        except Exception as e:
            return f"Error getting database summary: {str(e)}"


class AnalyzeDataInput(BaseModel):
    analysis_task: str = Field(..., description="The analysis task to perform.")


class AnalyzeData(BaseTool):
    name: str = "analyze_data"
    description: str = "LAST RESORT ONLY: Use this tool only after you've already used other tools to gather specific information."
    args_schema: Type[BaseModel] = AnalyzeDataInput

    def _run(self, analysis_task: str) -> str:
        return f"WARNING: You should use specific tools first before using analyze_data. For the task: '{analysis_task}', consider using tools like get_class_summary, get_class_info, get_class_relationship, search_class_info, or read_file to gather concrete information first."


# --- New Tool for Semantic Search ---
class CodebaseSemanticSearchInput(BaseModel):
    query: str = Field(...,
                       description="The natural language query describing the business domain or functionality to search for. Example: 'Manages user profiles, authentication, and shopping carts.'")

class CodebaseSemanticSearch(BaseTool):
    name: str = "codebase_semantic_search"
    description: str = "Search for classes (in the class summaries file) that are semantically related to a natural language query. Use this to find candidate classes for a business domain."
    args_schema: Type[BaseModel] = CodebaseSemanticSearchInput
    _model: Any = None
    _class_summaries: list = []
    _class_embeddings: Any = None

    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        # Don't load embeddings at initialization time anymore

    def _load_and_embed_summaries(self):
        """Loads class summaries and pre-computes their embeddings."""
        print("Loading and embedding class summaries for semantic search...")
        try:
            app_name = APP_CONFIG["app_name"]
            context_dir = os.path.join(WORKING_DIR, "context", app_name)
            summaries_file = os.path.join(context_dir, "class_summaries.json")
            
            if not os.path.exists(summaries_file):
                print(f"Warning: Summaries file not found at {summaries_file}. Semantic search will not work.")
                return

            with open(summaries_file, 'r') as f:
                data = json.load(f)
                # Handle both formats: direct dictionary or nested under "class_summaries"
                if "class_summaries" in data:
                    self._class_summaries = data.get("class_summaries", [])
                else:
                    # Convert dictionary to list format
                    self._class_summaries = [
                        {"class_name": class_name, "summary": class_data.get("summary", "")}
                        for class_name, class_data in data.items()
                    ]
            
            if not self._class_summaries:
                print("Warning: No class summaries found in the file. Semantic search will be empty.")
                return

            # Using a pre-trained model for code-related tasks is ideal
            self._model = SentenceTransformer('all-MiniLM-L6-v2')
            
            # Create embeddings for all class summaries
            descriptions = [summary.get('summary', '') for summary in self._class_summaries]
            self._class_embeddings = self._model.encode(descriptions, show_progress_bar=True)
            print("Finished embedding class summaries.")

        except Exception as e:
            print(f"Error during semantic search model initialization: {e}")

    def _run(self, query: str) -> str:
        # Lazy load the embeddings only when the tool is actually used
        if self._class_embeddings is None:
            self._load_and_embed_summaries()
            
        if not self._class_summaries or self._class_embeddings is None:
            return "Error: Semantic search is not available. Class summaries could not be loaded or embedded."

        try:
            # Embed the query
            query_embedding = self._model.encode([query])

            # Calculate cosine similarity
            similarities = cosine_similarity(query_embedding, self._class_embeddings)[0]

            # Get domain count from domain_clusters.json
            domain_count = 6  # Default value
            try:
                app_name = APP_CONFIG["app_name"]
                model_name = APP_CONFIG["model_name"]
                domain_clusters_path = os.path.join(WORKING_DIR, "output", app_name, model_name, "domains", "domain_clusters.json")
                
                if os.path.exists(domain_clusters_path):
                    with open(domain_clusters_path, 'r') as f:
                        domain_data = json.load(f)
                        if "business_domains" in domain_data:
                            domain_count = len(domain_data["business_domains"])
                            print(f"Found {domain_count} domains in {domain_clusters_path}")
                        else:
                            print(f"No business_domains key found in {domain_clusters_path}, using default domain count")
                else:
                    print(f"domain_clusters.json not found at {domain_clusters_path}, using default domain count")
            except Exception as e:
                print(f"Error reading domain clusters: {e}, using default domain count of {domain_count}")

            # Calculate top_n dynamically: max(5, total_class_num/domain_num)
            total_class_num = len(self._class_summaries)
            top_n = max(5, int(total_class_num / domain_count))
            print(f"Using top_n={top_n} for semantic search (total_class_num={total_class_num}, domain_count={domain_count})")
            
            # Get top N results
            top_indices = np.argsort(similarities)[-top_n:][::-1]

            results = []
            for idx in top_indices:
                similarity_score = similarities[idx]
                if similarity_score > 0.3: # Threshold to filter out irrelevant results
                    class_summary = self._class_summaries[idx]
                    results.append({
                        "class_name": class_summary.get("class_name"),
                        "summary": class_summary.get("summary"),
                        "similarity": f"{similarity_score:.4f}"
                    })

            if not results:
                return "No semantically relevant classes found for your query."
            
            return json.dumps(results, indent=2) + "\n\nNote: Use BOTH get_related_class_list and codebase_semantic_search to get more comprehensive results. BUT you should note that they may contain classes that do not belong to the current domain, you should carefully consider and exclude the classes of other domains."

        except Exception as e:
            return f"Error during semantic search: {e}"


# --- New Tools ---

class GetAllClassHierarchy(BaseTool):
    name: str = "get_all_class_hierarchy"
    description: str = "Get all classes names grouped by package, in a natural language format."
    args_schema: Type[BaseModel] = NoArgsToolInput

    def _run(self) -> str:
        try:
            app_name = APP_CONFIG["app_name"]
            context_dir = os.path.join(WORKING_DIR, "context", app_name)
            class_info_file = os.path.join(context_dir, "class_info_dependency.json")

            if not os.path.exists(class_info_file):
                return f"Error: Class info file not found at {class_info_file}"

            with open(class_info_file, 'r', encoding='utf-8') as f:
                class_info = json.load(f)

            packages = defaultdict(list)
            excluded_count = 0
            for class_name in sorted(class_info.keys()):
                try:
                    package_name = '.'.join(class_name.split('.')[:-1])
                    simple_class_name = class_name.split('.')[-1]
                    
                    # Check if the class has empty relationships
                    has_relationships = class_info[class_name].get("relationships") and len(class_info[class_name].get("relationships", {})) > 0
                    
                    if not has_relationships:
                        simple_class_name += " (isolated class)"
                        excluded_count += 1
                        
                    if not package_name: # Handle classes in default package
                        package_name = "(default package)"
                    packages[package_name].append(simple_class_name)
                except IndexError:
                    packages["(unknown package)"].append(class_name)

            result = ["All classes grouped by package:"]
            for package_name, classes in sorted(packages.items()):
                result.append(f"\nPackage: {package_name}")
                for cls in sorted(classes):
                    result.append(f"  - {cls}")
            
            # Add note about excluded classes
            if excluded_count > 0:
                result.append(f"\nSome classes ({excluded_count}) don't have any explicit dependency in the dependency graph, which are labeled as isolated.")
            
            return "\n".join(result)
        except Exception as e:
            return f"Error getting all classes: {str(e)}"

class GetAllClassHierarchyComplete(BaseTool):
    name: str = "get_all_class_hierarchy_complete"
    description: str = "Get all classes names grouped by package. This is a complete view of all classes in the system."
    args_schema: Type[BaseModel] = NoArgsToolInput

    def _run(self) -> str:
        try:
            app_name = APP_CONFIG["app_name"]
            context_dir = os.path.join(WORKING_DIR, "context", app_name)
            class_info_file = os.path.join(context_dir, "class_info_dependency.json")

            if not os.path.exists(class_info_file):
                return f"Error: Class info file not found at {class_info_file}"

            with open(class_info_file, 'r', encoding='utf-8') as f:
                class_info = json.load(f)

            packages = defaultdict(list)
            # excluded_count = 0
            for class_name in sorted(class_info.keys()):
                try:
                    package_name = '.'.join(class_name.split('.')[:-1])
                    simple_class_name = class_name.split('.')[-1]
                    
                    # Check if the class has empty relationships
                    has_relationships = class_info[class_name].get("relationships") and len(class_info[class_name].get("relationships", {})) > 0
                    
                    # if not has_relationships:
                    #     simple_class_name += " (currently excluded)"
                    #     excluded_count += 1
                        
                    if not package_name: # Handle classes in default package
                        package_name = "(default package)"
                    packages[package_name].append(simple_class_name)
                except IndexError:
                    packages["(unknown package)"].append(class_name)

            result = ["All classes grouped by package:"]
            for package_name, classes in sorted(packages.items()):
                result.append(f"\nPackage: {package_name}")
                for cls in sorted(classes):
                    result.append(f"  - {cls}")
            
            # Add note about excluded classes
            # if excluded_count > 0:
            #     result.append(f"\nSome classes ({excluded_count}) don't have any explicit dependency, at current stage not considered.")
            
            return "\n".join(result)
        except Exception as e:
            return f"Error getting all classes: {str(e)}"

class GetRelatedClassListInput(BaseModel):
    class_names: List[str] = Field(..., description="A list of full class names to find relations for.")

class GetRelatedClassList(BaseTool):
    name: str = "get_related_class_list"
    description: str = "For a list of classes, find all classes they depend on and all classes that depend on them, and return the unique union."
    args_schema: Type[BaseModel] = GetRelatedClassListInput
    _class_info: dict = None
    _inverted_deps: dict = None

    def _load_dependencies(self):
        if self._class_info is None:
            app_name = APP_CONFIG["app_name"]
            context_dir = os.path.join(WORKING_DIR, "context", app_name)
            class_info_file = os.path.join(context_dir, "class_info_dependency.json")
            if not os.path.exists(class_info_file):
                raise FileNotFoundError(f"Class info file not found at {class_info_file}")
            with open(class_info_file, 'r', encoding='utf-8') as f:
                self._class_info = json.load(f)

            # Build inverted dependency index
            self._inverted_deps = defaultdict(set)
            for class_name, data in self._class_info.items():
                if "relationships" in data:
                    for rel_type, targets in data["relationships"].items():
                        for target in targets:
                            self._inverted_deps[target].add(class_name)

    def _run(self, class_names: List[str]) -> str:
        try:
            self._load_dependencies()
            related_classes = set()

            for class_name in class_names:
                if class_name not in self._class_info:
                    # Maybe just warn and continue
                    continue
                
                related_classes.add(class_name)

                # Add outgoing dependencies
                if "relationships" in self._class_info.get(class_name, {}):
                    for rel_type, targets in self._class_info[class_name]["relationships"].items():
                        related_classes.update(targets)

                # Add incoming dependencies
                if class_name in self._inverted_deps:
                    related_classes.update(self._inverted_deps[class_name])
            
            return json.dumps(sorted(list(related_classes)), indent=2) + "\n\nNote: Use BOTH get_related_class_list and codebase_semantic_search(if applicable) to get more comprehensive results. BUT you should note that they may contain classes that do not belong to the current domain, you should carefully consider and exclude the classes of other domains."
        except Exception as e:
            return f"Error getting related class list: {str(e)}"


class RankDependencyEntropyAndRatio(BaseTool):
    name: str = "rank_dependency_entropy"
    description: str = "Calculates both incoming and outgoing dependency entropy for all classes. Incoming entropy is based on the diversity of business domains that depend on a class, while outgoing entropy is based on the diversity of business domains that the class depends on. Ranks classes and returns those in the top third with entropy > 0."
    args_schema: Type[BaseModel] = NoArgsToolInput

    def _run(self) -> str:
        try:
            app_name = APP_CONFIG["app_name"]
            
            # 1. Load domain-to-class mappings
            domain_dir = os.path.join(WORKING_DIR, "output", app_name, APP_CONFIG["model_name"], "domains")
            if not os.path.isdir(domain_dir):
                return f"Error: Domain directory not found at {domain_dir}. Run the merging task first."
            
            # First try to load from individual domain files
            domain_files = glob.glob(os.path.join(domain_dir, "*.json"))
            if not domain_files:
                return f"Error: No domain files found in {domain_dir}. Cannot calculate entropy."

            # Check if merged_domains.json exists and use it preferentially
            merged_domains_path = os.path.join(domain_dir, "merged_domains.json")
            class_to_domain = {}
            
            if os.path.exists(merged_domains_path):
                try:
                    with open(merged_domains_path, 'r') as f:
                        merged_domains = json.load(f)
                        
                    # Process the merged domains structure
                    domain_clusters = {}
                    if "Domain_Cluster" in merged_domains:
                        domain_clusters = merged_domains["Domain_Cluster"]
                    else:
                        # If the output doesn't have the expected "Domain_Cluster" key, 
                        # assume it's directly a map of domain names to class lists
                        domain_clusters = merged_domains
                    
                    for domain_name, class_list in domain_clusters.items():
                        if isinstance(class_list, list):
                            for cls in class_list:
                                class_to_domain[cls] = domain_name
                        elif isinstance(class_list, dict):
                            # Handle the case where each domain has layers
                            for layer, classes in class_list.items():
                                if isinstance(classes, list):
                                    for cls in classes:
                                        class_to_domain[cls] = domain_name
                    
                    # If we successfully loaded classes from merged domains, we can proceed
                    if class_to_domain:
                        print(f"Successfully loaded {len(class_to_domain)} classes from merged_domains.json")
                    else:
                        print("No classes found in merged_domains.json, falling back to individual domain files")
                except Exception as e:
                    print(f"Error loading merged domains: {e}, falling back to individual domain files")
            
            # # If merged_domains.json didn't exist or was empty, use individual domain files
            # if not class_to_domain:
            #     for domain_file in domain_files:
            #         # Skip the merged domains file if we're processing individual files
            #         if os.path.basename(domain_file) == "merged_domains.json":
            #             continue
                        
            #         domain_name = os.path.splitext(os.path.basename(domain_file))[0]
            #         try:
            #             with open(domain_file, 'r') as f:
            #                 domain_classes = json.load(f)
                            
            #                 # Handle both list format and dictionary format
            #                 if isinstance(domain_classes, list):
            #                     for cls in domain_classes:
            #                         class_to_domain[cls] = domain_name
            #                 elif isinstance(domain_classes, dict) and domain_name in domain_classes:
            #                     # Handle case where the file contains {domain_name: {layer: [classes]}}
            #                     layers_data = domain_classes[domain_name]
            #                     if isinstance(layers_data, dict):
            #                         for layer, classes in layers_data.items():
            #                             if isinstance(classes, list):
            #                                 for cls in classes:
            #                                     class_to_domain[cls] = domain_name
            #         except Exception as e:
            #             print(f"Error processing domain file {domain_file}: {e}")

            # if not class_to_domain:
            #     return f"Error: Could not load any domain-to-class mappings from {domain_dir}."

            # 2. Load class dependencies and create dependency map
            context_dir = os.path.join(WORKING_DIR, "context", app_name)
            class_info_file = os.path.join(context_dir, "class_info_dependency.json")
            if not os.path.exists(class_info_file):
                return f"Error: Class info file not found at {class_info_file}"
            
            with open(class_info_file, 'r', encoding='utf-8') as f:
                class_info = json.load(f)
            
            # Track which domains depend on each class (for incoming entropy)
            class_to_dependent_domains_incoming = defaultdict(list)
            
            # Track which domains each class depends on (for outgoing entropy)
            class_to_dependent_domains_outgoing = defaultdict(list)
            
            # Track classes that depend on each class (incoming dependencies)
            class_incoming_deps = defaultdict(set)
            
            # Track classes that each class depends on (outgoing dependencies)
            class_outgoing_deps = defaultdict(set)

            for class_name, class_data in class_info.items():
                if "relationships" in class_data:
                    # Check each relationship type
                    for rel_type, targets in class_data["relationships"].items():
                        # Check if this relationship type is in VALID_RELATIONSHIP_TYPES
                        is_valid = rel_type.upper() in VALID_RELATIONSHIP_TYPES or any(rel_type.upper().endswith(vrt) for vrt in VALID_RELATIONSHIP_TYPES)
                        
                        # Check if this relationship type is in VALID_INVERTED_RELATIONSHIP_TYPES
                        is_valid_inverted = rel_type.upper() in VALID_INVERTED_RELATIONSHIP_TYPES or any(rel_type.upper().endswith(vrt) for vrt in VALID_INVERTED_RELATIONSHIP_TYPES)
                        
                        # Count the number of target classes for each type
                        if is_valid:
                            # Count the number of target classes
                            if isinstance(targets, list):
                                class_outgoing_deps[class_name].update(targets)
                            elif isinstance(targets, dict):
                                class_outgoing_deps[class_name].update(targets.keys())
                        
                        if is_valid_inverted:
                            # Count the number of target classes
                            if isinstance(targets, list):
                                class_incoming_deps[class_name].update(targets)
                            elif isinstance(targets, dict):
                                class_incoming_deps[class_name].update(targets.keys())

            
            # For each class in our domains
            for source_class, source_domain in class_to_domain.items():
                if source_class not in class_info:
                    continue
                    
                # Get its dependencies
                if "relationships" in class_info[source_class]:
                    for rel_type, targets in class_info[source_class]["relationships"].items():
                        # Skip relationship types that are not in our valid list
                        if rel_type.upper() not in VALID_RELATIONSHIP_TYPES and not any(rel_type.upper().endswith(vrt) for vrt in VALID_RELATIONSHIP_TYPES):
                            continue
                            
                        for target_class in targets:
                            # For each target class, record that source_domain depends on it (incoming for target)
                            class_to_dependent_domains_incoming[target_class].append(source_domain)
                            

            
            # Process outgoing dependency domains separately to ensure we capture all classes that depend on domains
            for source_class in class_info:
                if "relationships" in class_info[source_class]:
                    for rel_type, targets in class_info[source_class]["relationships"].items():
                        # Skip relationship types that are not in our valid list
                        if rel_type.upper() not in VALID_RELATIONSHIP_TYPES and not any(rel_type.upper().endswith(vrt) for vrt in VALID_RELATIONSHIP_TYPES):
                            continue
                            
                        for target_class in targets:
                            # Only process if the target class is in a known domain
                            if target_class in class_to_domain:
                                target_domain = class_to_domain[target_class]
                                # Record that source_class depends on target_domain (outgoing for source)
                                class_to_dependent_domains_outgoing[source_class].append(target_domain)
                                

            
            # 3. Calculate entropy for each class based on dependent domains (incoming)
            class_entropies_incoming = {}
            class_dependency_ratios = {}
            
            for class_name, dependent_domains in class_to_dependent_domains_incoming.items():
                # Count occurrences of each domain
                domain_counts = defaultdict(int)
                for domain in dependent_domains:
                    domain_counts[domain] += 1
                
                # Skip if no domains depend on this class
                if not domain_counts or sum(domain_counts.values()) == 0:
                    continue
                
                total_deps = sum(domain_counts.values())
                entropy = 0.0
                for count in domain_counts.values():
                    probability = count / total_deps
                    entropy -= probability * math.log2(probability)
                
                class_entropies_incoming[class_name] = entropy
                
                # Calculate dependency ratio: incoming dependencies / outgoing dependencies
                num_incoming = len(class_incoming_deps[class_name])
                num_outgoing = len(class_outgoing_deps[class_name])
                
                # Avoid division by zero
                if num_outgoing > 0:
                    ratio = num_incoming / num_outgoing
                else:
                    # If no outgoing dependencies, use a high value to indicate this is potentially a leaf class
                    ratio = float('inf') if num_incoming > 0 else 0
                
                class_dependency_ratios[class_name] = ratio

            # 4. Calculate entropy for each class based on dependent domains (outgoing)
            class_entropies_outgoing = {}
            outgoing_dependency_ratios = {}
            
            for class_name, dependent_domains in class_to_dependent_domains_outgoing.items():
                # Count occurrences of each domain
                domain_counts = defaultdict(int)
                for domain in dependent_domains:
                    domain_counts[domain] += 1
                
                # Skip if this class doesn't depend on any domains
                if not domain_counts or sum(domain_counts.values()) == 0:
                    continue
                
                total_deps = sum(domain_counts.values())
                entropy = 0.0
                for count in domain_counts.values():
                    probability = count / total_deps
                    entropy -= probability * math.log2(probability)
                
                class_entropies_outgoing[class_name] = entropy
                
                # Calculate outgoing dependency ratio: outgoing dependencies / incoming dependencies
                num_incoming = len(class_incoming_deps[class_name])
                num_outgoing = len(class_outgoing_deps[class_name])
                
                # Avoid division by zero
                if num_incoming > 0:
                    ratio = num_outgoing / num_incoming
                else:
                    # If no incoming dependencies, use a high value to indicate this is potentially a root class
                    ratio = float('inf') if num_outgoing > 0 else 0
                
                outgoing_dependency_ratios[class_name] = ratio

            # 5. Rank and return top classes with entropy > 0 for incoming dependencies
            if not class_entropies_incoming:
                incoming_result = "Could not calculate incoming dependency entropy for any classes."
            else:
                # Create a list of tuples with (class_name, entropy, ratio)
                class_metrics_incoming = [(cls, ent, class_dependency_ratios.get(cls, 0)) 
                                for cls, ent in class_entropies_incoming.items()]
                
                # First sort by entropy in descending order
                sorted_classes_incoming = sorted(class_metrics_incoming, key=lambda item: (item[1], item[2]), reverse=True)
                
                # Take the top 1/3 first, handling ties at the boundary
                target_count_incoming = max(1, len(sorted_classes_incoming) // 3)
                
                if target_count_incoming >= len(sorted_classes_incoming):
                    # If target count is >= total classes, take all
                    top_third_classes_incoming = sorted_classes_incoming
                else:
                    # Find the entropy value at the cutoff point
                    cutoff_entropy_incoming = sorted_classes_incoming[target_count_incoming - 1][1]
                    cutoff_entropy_str_incoming = f"{cutoff_entropy_incoming:.6f}"  # Round to 6 decimal places for comparison
                    
                    # Include all classes with entropy >= cutoff_entropy to handle ties
                    top_third_classes_incoming = [(cls, ent, ratio) for cls, ent, ratio in sorted_classes_incoming 
                                        if f"{ent:.6f}" >= cutoff_entropy_str_incoming]
                
                # Then filter to keep only those with entropy > 0
                final_classes_incoming = [(cls, ent, ratio) for cls, ent, ratio in top_third_classes_incoming if ent > 0]
                
                if not final_classes_incoming:
                    incoming_result = "No classes found in the top third with incoming entropy > 0."
                else:
                    incoming_result = {
                        "ranked_classes_by_incoming_entropy": [
                            {
                                "class_name": cls, 
                                "entropy": round(ent, 4),
                                "incoming dependency_ratio": float('inf') if ratio == float('inf') else round(ratio, 4),
                                "number of classes depending on this class": len(class_incoming_deps[cls]),
                                "number of classes this class depends on": len(class_outgoing_deps[cls])
                            } 
                            for cls, ent, ratio in final_classes_incoming
                        ],
                        "note": "These classes are used by multiple domains. Incoming entropy measures how evenly a class is used across different domains. Higher entropy suggests the class is a better candidate for being a common entity/utility/base class."
                    }

            # 6. Rank and return top classes with entropy > 0 for outgoing dependencies
            if not class_entropies_outgoing:
                outgoing_result = "Could not calculate outgoing dependency entropy for any classes."
            else:
                # Create a list of tuples with (class_name, entropy)
                class_metrics_outgoing = [(cls, ent, outgoing_dependency_ratios.get(cls, 0)) 
                                        for cls, ent in class_entropies_outgoing.items()]
                
                # Sort by entropy in descending order, then by ratio in descending order
                sorted_classes_outgoing = sorted(class_metrics_outgoing, key=lambda item: (item[1], item[2]), reverse=True)
                
                # Take the top 1/3 first, handling ties at the boundary
                target_count_outgoing = max(1, len(sorted_classes_outgoing) // 3)
                
                if target_count_outgoing >= len(sorted_classes_outgoing):
                    # If target count is >= total classes, take all
                    top_third_classes_outgoing = sorted_classes_outgoing
                else:
                    # Find the entropy value at the cutoff point
                    cutoff_entropy_outgoing = sorted_classes_outgoing[target_count_outgoing - 1][1]
                    cutoff_entropy_str_outgoing = f"{cutoff_entropy_outgoing:.6f}"  # Round to 6 decimal places for comparison
                    
                    # Include all classes with entropy >= cutoff_entropy to handle ties
                    top_third_classes_outgoing = [(cls, ent, ratio) for cls, ent, ratio in sorted_classes_outgoing 
                                        if f"{ent:.6f}" >= cutoff_entropy_str_outgoing]
                
                # Then filter to keep only those with entropy > 0
                final_classes_outgoing = [(cls, ent, ratio) for cls, ent, ratio in top_third_classes_outgoing if ent > 0]
                
                if not final_classes_outgoing:
                    outgoing_result = "No classes found in the top third with outgoing entropy > 0."
                else:
                    outgoing_result = {
                        "ranked_classes_by_outgoing_entropy": [
                            {
                                "class_name": cls, 
                                "entropy": round(ent, 4),
                                "outgoing_dependency_ratio": float('inf') if ratio == float('inf') else round(ratio, 4),
                                "number of classes this class depends on": len(class_outgoing_deps[cls]),
                                "number of classes depending on this class": len(class_incoming_deps[cls])
                            } 
                            for cls, ent, ratio in final_classes_outgoing
                        ],
                        "note": "These classes depend on multiple domains. Outgoing entropy measures how evenly a class depends on different domains. Outgoing dependency ratio is the number of classes this class depends on divided by the number of classes that depend on it. Higher values for BOTH metrics suggest the class might be a coordinator or facade that serves multiple domains."
                    }

            # 7. Combine results
            result = {
                "incoming_dependency_entropy": incoming_result,
                "outgoing_dependency_entropy": outgoing_result,
                "Tips": "After using this rank_dependency_entropy tool to discover possible classes, always use get_more_potential_common_classes to discover more potential common classes."
            }

            return json.dumps(result, indent=2)

        except Exception as e:
            return f"Error calculating dependency entropy and ratio: {str(e)}"


class AnalyzeDomainCohesion(BaseTool):
    name: str = "analyze_domain_cohesion"
    description: str = "Analyzes the cohesion between domains based on their dependencies and shared classes. Helps identify which domains should be merged together to form high-cohesive, low-coupling microservices."
    args_schema: Type[BaseModel] = NoArgsToolInput

    def _run(self) -> str:
        try:
            app_name = APP_CONFIG["app_name"]
            
            # 1. Load domain-to-class mappings
            domain_dir = os.path.join(WORKING_DIR, "output", app_name, APP_CONFIG["model_name"], "domains")
            if not os.path.isdir(domain_dir):
                return f"Error: Domain directory not found at {domain_dir}. Run the aggregation task first."
            
            # First try to load from individual domain files
            domain_files = glob.glob(os.path.join(domain_dir, "*.json"))
            if not domain_files:
                return f"Error: No domain files found in {domain_dir}. Cannot analyze domain cohesion."
            
            # Load classes for each domain
            domain_to_classes = {}
            for domain_file in domain_files:
                # Skip the merged domains file
                if os.path.basename(domain_file) == "merged_domains.json":
                    continue
                    
                domain_name = os.path.splitext(os.path.basename(domain_file))[0]
                try:
                    with open(domain_file, 'r') as f:
                        domain_classes = json.load(f)
                        
                        # Handle both list format and dictionary format
                        if isinstance(domain_classes, list):
                            domain_to_classes[domain_name] = domain_classes
                        elif isinstance(domain_classes, dict) and domain_name in domain_classes:
                            # Handle case where the file contains {domain_name: {layer: [classes]}}
                            layers_data = domain_classes[domain_name]
                            all_classes = []
                            if isinstance(layers_data, dict):
                                for layer, classes in layers_data.items():
                                    if isinstance(classes, list):
                                        all_classes.extend(classes)
                            domain_to_classes[domain_name] = all_classes
                except Exception as e:
                    print(f"Error processing domain file {domain_file}: {e}")
            
            if not domain_to_classes:
                return f"Error: Could not load any domain-to-class mappings from {domain_dir}."
            
            # 2. Load class dependencies
            context_dir = os.path.join(WORKING_DIR, "context", app_name)
            class_info_file = os.path.join(context_dir, "class_info_dependency.json")
            if not os.path.exists(class_info_file):
                return f"Error: Class info file not found at {class_info_file}"
            
            with open(class_info_file, 'r', encoding='utf-8') as f:
                class_info = json.load(f)
            
            # 3. Calculate domain-to-domain dependencies
            domain_dependencies = defaultdict(lambda: defaultdict(int))
            
            # For each domain and its classes
            for source_domain, source_classes in domain_to_classes.items():
                for source_class in source_classes:
                    if source_class not in class_info:
                        continue
                    
                    # Get its dependencies
                    if "relationships" in class_info[source_class]:
                        for rel_type, targets in class_info[source_class]["relationships"].items():
                            # Skip relationship types that are not in our valid list
                            if rel_type.upper() not in VALID_RELATIONSHIP_TYPES and not any(rel_type.upper().endswith(vrt) for vrt in VALID_RELATIONSHIP_TYPES):
                                continue
                                
                            for target_class in targets:
                                # Find which domain the target class belongs to
                                for target_domain, target_classes in domain_to_classes.items():
                                    if target_class in target_classes and target_domain != source_domain:
                                        # Increment dependency count
                                        domain_dependencies[source_domain][target_domain] += 1
            
            # 4. Calculate shared classes between domains
            domain_shared_classes = defaultdict(lambda: defaultdict(list))
            all_classes = set()
            for domain, classes in domain_to_classes.items():
                all_classes.update(classes)
            
            # Create a map of class to domains
            class_to_domains = defaultdict(list)
            for domain, classes in domain_to_classes.items():
                for cls in classes:
                    class_to_domains[cls].append(domain)
            
            # Find classes shared between domains
            for cls, domains in class_to_domains.items():
                if len(domains) > 1:
                    for i, domain1 in enumerate(domains):
                        for domain2 in domains[i+1:]:
                            domain_shared_classes[domain1][domain2].append(cls)
                            domain_shared_classes[domain2][domain1].append(cls)
            
            # 5. Calculate cohesion scores between domains
            domain_cohesion = {}
            for domain1 in domain_to_classes.keys():
                domain_cohesion[domain1] = {}
                for domain2 in domain_to_classes.keys():
                    if domain1 == domain2:
                        continue
                    
                    # Calculate cohesion score based on dependencies and shared classes
                    dep_score = domain_dependencies[domain1][domain2] + domain_dependencies[domain2][domain1]
                    shared_score = len(domain_shared_classes[domain1][domain2])
                    
                    # Normalize by domain sizes
                    size_factor = (len(domain_to_classes[domain1]) + len(domain_to_classes[domain2])) / 2
                    if size_factor > 0:
                        normalized_score = (dep_score + shared_score) / size_factor
                    else:
                        normalized_score = 0
                    
                    domain_cohesion[domain1][domain2] = {
                        "cohesion_score": round(normalized_score, 4),
                        "dependencies": dep_score,
                        "shared_classes": shared_score
                    }
            
            # 6. Find top domain pairs by cohesion score
            domain_pairs = []
            for domain1 in domain_cohesion:
                for domain2, scores in domain_cohesion[domain1].items():
                    if domain1 < domain2:  # Avoid duplicates
                        domain_pairs.append((domain1, domain2, scores["cohesion_score"]))
            
            # Sort pairs by cohesion score (highest first)
            domain_pairs.sort(key=lambda x: x[2], reverse=True)
            
            # 7. Prepare result
            result = {
                "domain_cohesion_analysis": {
                    "domain_pairs_by_cohesion": [
                        {
                            "domains": [d1, d2],
                            "cohesion_score": score,
                            "details": domain_cohesion[d1][d2]
                        }
                        for d1, d2, score in domain_pairs[:10]  # Top 10 pairs
                    ],
                    "domain_dependencies": {
                        d1: {d2: count for d2, count in deps.items() if count > 0}
                        for d1, deps in domain_dependencies.items()
                    },
                    "domain_shared_classes": {
                        d1: {d2: len(classes) for d2, classes in shared.items() if classes}
                        for d1, shared in domain_shared_classes.items()
                    }
                }
            }
            
            return json.dumps(result, indent=2)
            
        except Exception as e:
            return f"Error analyzing domain cohesion: {str(e)}"


class GetClassDependencyInput(BaseModel):
    class_name: str = Field(...,
                          description="The full name of the class (including package) to get dependency information for. Example: org.springframework.samples.petclinic.model.Pet")


class GetClassDependency(BaseTool):
    name: str = "get_class_dependency"
    description: str = "Extracts complete dependency information for a class from class_info_dependency.json, showing both classes that depend on the input class and classes that the input class depends on."
    args_schema: Type[BaseModel] = GetClassDependencyInput
    _class_info: dict = None
    _inverted_deps: dict = None

    def _load_dependencies(self, app_name):
        """Loads the class_info_dependency.json file and builds an inverted dependency index."""
        if self._class_info is None:
            context_dir = os.path.join(WORKING_DIR, "context", app_name)
            class_info_file = os.path.join(context_dir, "class_info_dependency.json")
            if not os.path.exists(class_info_file):
                raise FileNotFoundError(f"Class info file not found at {class_info_file}")
            
            with open(class_info_file, 'r', encoding='utf-8') as f:
                self._class_info = json.load(f)

            # Build inverted dependency index
            self._inverted_deps = defaultdict(lambda: defaultdict(list))
            for source_class, data in self._class_info.items():
                if "relationships" in data:
                    for rel_type, targets in data["relationships"].items():
                        for target in targets:
                            self._inverted_deps[target][rel_type].append(source_class)

    def _run(self, class_name: str) -> str:
        try:
            app_name = APP_CONFIG["app_name"]
            self._load_dependencies(app_name)
            
            if class_name not in self._class_info:
                return f"Class '{class_name}' not found in class_info_dependency.json"
            
            result = {
                "class": class_name,
                "outgoing_dependencies": {},
                "incoming_dependencies": {}
            }
            
            # Get outgoing dependencies (classes this class depends on)
            if "relationships" in self._class_info[class_name]:
                for rel_type, targets in self._class_info[class_name]["relationships"].items():
                    if targets:  # Only include non-empty relationship types
                        result["outgoing_dependencies"][rel_type] = targets
            
            # Get incoming dependencies (classes that depend on this class)
            if class_name in self._inverted_deps:
                for rel_type, sources in self._inverted_deps[class_name].items():
                    if sources:  # Only include non-empty relationship types
                        result["incoming_dependencies"][rel_type] = sources
            
            # Add summary counts
            outgoing_count = sum(len(deps) for deps in result["outgoing_dependencies"].values())
            incoming_count = sum(len(deps) for deps in result["incoming_dependencies"].values())
            
            result["summary"] = {
                "total_outgoing_dependencies": outgoing_count,
                "total_incoming_dependencies": incoming_count,
                "dependency_ratio": round(incoming_count / max(1, outgoing_count), 2),
                "total_dependencies": outgoing_count + incoming_count
            }
            
            return json.dumps(result, indent=2)
            
        except Exception as e:
            return f"Error getting class dependency information: {str(e)}"


class GetClassRelationAndCodeInput(BaseModel):
    class_name: str = Field(...,
                          description="The full name of the class (including package) to get relationship and source code for. Example: org.springframework.samples.petclinic.model.Pet")


class GetClassRelationAndCode(BaseTool):
    name: str = "get_class_relation_and_code"
    description: str = "Get both the relationships and source code of a class by its full name. Shows dependencies and implementation details in one view. The number represents the count of this relationship detected between two classes."
    args_schema: Type[BaseModel] = GetClassRelationAndCodeInput

    def _run(self, class_name: str) -> str:
        try:
            app_name = APP_CONFIG["app_name"]
            context_dir = os.path.join(WORKING_DIR, "context", app_name)
            class_info_file = os.path.join(context_dir, "class_info_dependency.json")

            if not os.path.exists(class_info_file):
                return f"Error: Class info file not found at {class_info_file}"

            # Part 1: Get class relationships
            relationship_result = ""
            try:
                with open(class_info_file, 'r', encoding='utf-8') as f:
                    class_info = json.load(f)

                if class_name not in class_info:
                    relationship_result = f"Class '{class_name}' not found in class_info_dependency.json"
                else:
                    class_data = class_info[class_name]
                    if not class_data.get("relationships"):
                        relationship_result = f"No relationships found for class '{class_name}'"
                    else:
                        result = [f"Relationships for {class_name}:"]
                        for rel_type, targets in class_data["relationships"].items():
                            result.append(f"\n{rel_type}:")
                            result.extend([f"  - {target}" for target in targets])
                        relationship_result = "\n".join(result)
            except Exception as e:
                relationship_result = f"Error getting class relationships: {str(e)}"

            # Part 2: Get source code
            source_code_result = ""
            try:
                summaries_file = os.path.join(context_dir, "class_summaries.json")
                if os.path.exists(summaries_file):
                    with open(summaries_file, 'r', encoding='utf-8') as f:
                        class_summaries = json.load(f)
                    if class_name in class_summaries and "file_path" in class_summaries[class_name]:
                        file_path = class_summaries[class_name]["file_path"]
                
                if file_path:
                    # Clean and resolve the path
                    file_path = clean_path(file_path)
                    if not os.path.isabs(file_path):
                        full_path = os.path.join(WORKING_DIR, file_path)
                        if not os.path.exists(full_path):
                            resource_path = os.path.join(WORKING_DIR, "resources", app_name, file_path)
                            if os.path.exists(resource_path):
                                full_path = resource_path
                        file_path = full_path
                    
                    # Read the file
                    if os.path.exists(file_path) and os.path.isfile(file_path):
                        with open(file_path, 'r', encoding='utf-8', errors='replace') as f:
                            source_code_result = f"Source code from {file_path}:\n\n{f.read()}"
                    else:
                        source_code_result = f"Could not find source file for class {class_name}"
                else:
                    source_code_result = f"Could not determine file path for class {class_name}"
            except Exception as e:
                source_code_result = f"Error getting source code: {str(e)}"

            # Combine results
            return f"<Class Dependency>\n{relationship_result}\n</Class Dependency>\n\n<Source Code>\n{source_code_result}\n</Source Code>"
            
        except Exception as e:
            return f"Error in GetClassRelationAndCode: {str(e)}"


class GetMultiClassRelationAndCodeInput(BaseModel):
    class_names: List[str] = Field(...,
                          description="A list of full class names (including packages) to get relationships and source code for. Example: ['org.springframework.samples.petclinic.model.Pet', 'org.springframework.samples.petclinic.model.Owner']")


class GetMultiClassRelationAndCode(BaseTool):
    name: str = "get_multi_class_relation_and_code"
    description: str = "Get both the relationships and source code for multiple classes by their full names. Shows dependencies and implementation details for each class in one view."
    args_schema: Type[BaseModel] = GetMultiClassRelationAndCodeInput

    def _run(self, class_names: List[str]) -> str:
        try:
            app_name = APP_CONFIG["app_name"]
            context_dir = os.path.join(WORKING_DIR, "context", app_name)
            class_info_file = os.path.join(context_dir, "class_info_dependency.json")

            if not os.path.exists(class_info_file):
                return f"Error: Class info file not found at {class_info_file}"
            
            # Load class info once
            with open(class_info_file, 'r', encoding='utf-8') as f:
                class_info = json.load(f)
                
            # Load class summaries if available
            class_summaries = {}
            summaries_file = os.path.join(context_dir, "class_summaries.json")
            if os.path.exists(summaries_file):
                with open(summaries_file, 'r', encoding='utf-8') as f:
                    class_summaries = json.load(f)

            results = []
            
            for class_name in class_names:
                class_result = {"class_name": class_name, "relationships": "", "source_code": ""}
                
                # Part 1: Get class relationships
                try:
                    if class_name not in class_info:
                        class_result["relationships"] = f"Class '{class_name}' not found in class_info_dependency.json"
                    else:
                        class_data = class_info[class_name]
                        if not class_data.get("relationships"):
                            class_result["relationships"] = f"No relationships found for class '{class_name}'"
                        else:
                            rel_lines = [f"Relationships for {class_name}:"]
                            for rel_type, targets in class_data["relationships"].items():
                                rel_lines.append(f"\n{rel_type}:")
                                rel_lines.extend([f"  - {target}" for target in targets])
                            class_result["relationships"] = "\n".join(rel_lines)
                except Exception as e:
                    class_result["relationships"] = f"Error getting class relationships: {str(e)}"

                # Part 2: Get source code
                try:
                    # First, try to find the file path from class_info
                    file_path = None
                    if class_name in class_info and "file_path" in class_info[class_name]:
                        file_path = class_info[class_name]["file_path"]
                    
                    # If not found in class_info, check class_summaries
                    if not file_path and class_name in class_summaries and "file_path" in class_summaries[class_name]:
                        file_path = class_summaries[class_name]["file_path"]
                    
                    # If still not found, try to construct from class name
                    if not file_path:
                        # Convert package.name.ClassName to package/name/ClassName.java
                        package_parts = class_name.split('.')
                        if len(package_parts) > 1:
                            class_file = package_parts[-1] + ".java"
                            package_path = "/".join(package_parts[:-1])
                            # Look in common source directories
                            possible_paths = [
                                f"resources/{app_name}/src/main/java/{package_path}/{class_file}",
                                f"resources/{app_name}/src/{package_path}/{class_file}",
                                f"resources/{app_name}/{package_path}/{class_file}"
                            ]
                            
                            for path in possible_paths:
                                full_path = os.path.join(WORKING_DIR, path)
                                if os.path.exists(full_path):
                                    file_path = path
                                    break
                    
                    if file_path:
                        # Clean and resolve the path
                        file_path = clean_path(file_path)
                        if not os.path.isabs(file_path):
                            full_path = os.path.join(WORKING_DIR, file_path)
                            if not os.path.exists(full_path):
                                resource_path = os.path.join(WORKING_DIR, "resources", app_name, file_path)
                                if os.path.exists(resource_path):
                                    full_path = resource_path
                            file_path = full_path
                        
                        # Read the file
                        if os.path.exists(file_path) and os.path.isfile(file_path):
                            with open(file_path, 'r', encoding='utf-8', errors='replace') as f:
                                class_result["source_code"] = f"Source code from {file_path}:\n\n{f.read()}"
                        else:
                            class_result["source_code"] = f"Could not find source file for class {class_name}"
                    else:
                        class_result["source_code"] = f"Could not determine file path for class {class_name}"
                except Exception as e:
                    class_result["source_code"] = f"Error getting source code: {str(e)}"
                
                # Format the result for this class
                formatted_result = f"=== {class_name} ===\n\n"
                formatted_result += f"<Class Dependency>\n{class_result['relationships']}\n</Class Dependency>\n\n"
                formatted_result += f"<Source Code>\n{class_result['source_code']}\n</Source Code>\n\n"
                formatted_result += "=" * 80 + "\n"
                
                results.append(formatted_result)
            
            # Combine all class results
            return "\n".join(results)
            
        except Exception as e:
            return f"Error in GetMultiClassRelationAndCode: {str(e)}"


class AnalyzeDomainRelationMetrics(BaseTool):
    name: str = "analyze_domain_relation_metrics"
    description: str = "Calculates the number of relations between every two domains, within each domain, and their ratio. Returns domain pairs ranked by cross-domain to intra-domain relation ratio."
    args_schema: Type[BaseModel] = NoArgsToolInput

    def _run(self) -> str:
        try:
            app_name = APP_CONFIG["app_name"]
            
            # 1. Load domain-to-class mappings
            domain_dir = os.path.join(WORKING_DIR, "output", app_name, APP_CONFIG["model_name"], "domains")
            if not os.path.isdir(domain_dir):
                return f"Error: Domain directory not found at {domain_dir}. Run the merging task first."
            
            # First try to load from individual domain files
            domain_files = glob.glob(os.path.join(domain_dir, "*.json"))
            if not domain_files:
                return f"Error: No domain files found in {domain_dir}. Cannot analyze domain relations."
            
            # Check if all_domains.json exists and use it preferentially
            all_domains_path = os.path.join(domain_dir, "all_domains.json")
            domain_to_classes = {}
            
            if os.path.exists(all_domains_path):
                try:
                    with open(all_domains_path, 'r') as f:
                        all_domains = json.load(f)
                    
                    # all_domains.json is expected to be a direct mapping of domain names to class lists
                    for domain_name, class_list in all_domains.items():
                        if isinstance(class_list, list):
                            domain_to_classes[domain_name] = class_list
                        elif isinstance(class_list, dict):
                            # Handle the case where each domain has layers
                            all_classes = []
                            for layer, classes in class_list.items():
                                if isinstance(classes, list):
                                    all_classes.extend(classes)
                            domain_to_classes[domain_name] = all_classes
                    
                    # If we successfully loaded classes from all_domains.json, we can proceed
                    if domain_to_classes:
                        print(f"Successfully loaded {len(domain_to_classes)} domains from all_domains.json")
                    else:
                        print("No classes found in all_domains.json, falling back to individual domain files")
                except Exception as e:
                    print(f"Error loading all domains: {e}, falling back to individual domain files")
            
            # If all_domains.json didn't exist or was empty, use individual domain files
            if not domain_to_classes:
                for domain_file in domain_files:
                    # Skip the all_domains.json file if we're processing individual files
                    if os.path.basename(domain_file) == "all_domains.json" or os.path.basename(domain_file) == "merged_domains.json":
                        continue
                        
                    domain_name = os.path.splitext(os.path.basename(domain_file))[0]
                    try:
                        with open(domain_file, 'r') as f:
                            domain_classes = json.load(f)
                            
                            # Handle both list format and dictionary format
                            if isinstance(domain_classes, list):
                                domain_to_classes[domain_name] = domain_classes
                            elif isinstance(domain_classes, dict) and domain_name in domain_classes:
                                # Handle case where the file contains {domain_name: {layer: [classes]}}
                                layers_data = domain_classes[domain_name]
                                all_classes = []
                                if isinstance(layers_data, dict):
                                    for layer, classes in layers_data.items():
                                        if isinstance(classes, list):
                                            all_classes.extend(classes)
                                domain_to_classes[domain_name] = all_classes
                    except Exception as e:
                        print(f"Error processing domain file {domain_file}: {e}")
            
            if not domain_to_classes:
                return f"Error: Could not load any domain-to-class mappings from {domain_dir}."
            
            # Create a map of class to domain for quick lookups
            class_to_domain = {}
            for domain, classes in domain_to_classes.items():
                for cls in classes:
                    class_to_domain[cls] = domain
            
            # 2. Load class dependencies and create relation counts
            context_dir = os.path.join(WORKING_DIR, "context", app_name)
            class_info_file = os.path.join(context_dir, "class_info_dependency.json")
            if not os.path.exists(class_info_file):
                return f"Error: Class info file not found at {class_info_file}"
            
            with open(class_info_file, 'r', encoding='utf-8') as f:
                class_info = json.load(f)
            
            # Initialize counters for relations
            # Format: domain_relations[source_domain][target_domain] = count
            domain_relations = defaultdict(lambda: defaultdict(int))
            
            # For each class in our domains
            for source_class, class_data in class_info.items():
                # Skip if the class is not in any domain
                if source_class not in class_to_domain:
                    continue
                
                source_domain = class_to_domain[source_class]
                
                # Get its relationships
                if "relationships" in class_data:
                    for rel_type, targets in class_data["relationships"].items():
                        # Skip relationship types that are not in our valid list
                        if rel_type.upper() not in VALID_RELATIONSHIP_TYPES and not any(rel_type.upper().endswith(vrt) for vrt in VALID_RELATIONSHIP_TYPES):
                            continue
                            
                        # Handle the new format where targets is a dictionary with counts
                        if isinstance(targets, dict):
                            for target_class, count in targets.items():
                                # Skip if the target class is not in any domain
                                if target_class not in class_to_domain:
                                    continue
                                
                                target_domain = class_to_domain[target_class]
                                
                                # Increment the relation count between domains by the actual count value
                                domain_relations[source_domain][target_domain] += count
                        
                        # Handle the old format where targets is a list
                        elif isinstance(targets, list):
                            for target_class in targets:
                                # Skip if the target class is not in any domain
                                if target_class not in class_to_domain:
                                    continue
                                
                                target_domain = class_to_domain[target_class]
                                
                                # Increment the relation count between domains
                                domain_relations[source_domain][target_domain] += 1
            
            # 3. Calculate metrics for each domain and domain pair
            domain_metrics = {}
            
            # Calculate intra-domain relations (within the same domain)
            intra_domain_relations = {domain: domain_relations[domain][domain] for domain in domain_to_classes.keys()}
            
            # Calculate total cross-domain relations for each domain
            domain_total_cross = {}
            for domain in domain_to_classes.keys():
                # Sum of all relations from this domain to other domains
                outgoing = sum(domain_relations[domain][other_domain] 
                              for other_domain in domain_to_classes.keys() 
                              if domain != other_domain)
                              
                # Sum of all relations from other domains to this domain
                incoming = sum(domain_relations[other_domain][domain] 
                              for other_domain in domain_to_classes.keys() 
                              if domain != other_domain)
                              
                # Total cross-domain relations for this domain
                domain_total_cross[domain] = outgoing + incoming
            
            # Calculate cross-domain relations and ratios for each domain pair
            domain_pairs = []
            
            for source_domain in domain_to_classes.keys():
                for target_domain in domain_to_classes.keys():
                    if source_domain >= target_domain:  # Skip self-relations and duplicates
                        continue
                    
                    # Get cross-domain relations (one-way counts)
                    source_to_target = domain_relations[source_domain][target_domain]
                    target_to_source = domain_relations[target_domain][source_domain]
                    
                    # Calculate total cross-domain relations for this pair
                    cross_domain_relations = source_to_target + target_to_source
                    
                    # Calculate ratios: cross-domain relations between the pair divided by 
                    # total cross-domain relations for each domain
                    source_ratio = 0
                    if domain_total_cross[source_domain] > 0:
                        source_ratio = cross_domain_relations / domain_total_cross[source_domain]
                        
                    target_ratio = 0
                    if domain_total_cross[target_domain] > 0:
                        target_ratio = cross_domain_relations / domain_total_cross[target_domain]
                    
                    # Use the higher ratio for ranking
                    max_ratio = max(source_ratio, target_ratio)
                    
                    # Store the metrics with detailed breakdown
                    domain_pairs.append({
                        "domains": [source_domain, target_domain],
                        "cross_domain_relations": {
                            f"{source_domain}_to_{target_domain}": source_to_target,
                            f"{target_domain}_to_{source_domain}": target_to_source,
                            "total": cross_domain_relations
                        },
                        "domain_total_cross": {
                            source_domain: domain_total_cross[source_domain],
                            target_domain: domain_total_cross[target_domain]
                        },
                        "ratios": {
                            f"{source_domain}_ratio": source_ratio,
                            f"{target_domain}_ratio": target_ratio,
                            "max_ratio": max_ratio
                        }
                    })
            
            # Sort domain pairs by the maximum ratio (high to low)
            domain_pairs.sort(key=lambda x: x["ratios"]["max_ratio"], reverse=True)
            
            # 4. Prepare the result
            result = {
                "domain_relation_metrics": {
                    "domain_pairs_by_ratio": domain_pairs,
                    "domain_total_cross": domain_total_cross,
                    "note": "Each domain pair has two ratios: the cross-domain relations between the pair divided by the total cross-domain relations for each domain. Pairs are ranked by the higher of these two ratios. Higher ratios indicate stronger coupling between the domains relative to their other dependencies."
                }
            }
            
            return json.dumps(result, indent=2)
            
        except Exception as e:
            return f"Error analyzing domain relation metrics: {str(e)}"


class DomainSemanticSimilarityInput(BaseModel):
    json_file_path: str = Field(default="all_domains.json", 
                                description="Path to the JSON file containing domain data. Default is 'all_domains.json'.")

class DomainSemanticSimilarity(BaseTool):
    name: str = "domain_semantic_similarity"
    description: str = "Calculate semantic similarity between all pairs of domains in a JSON file and return results ranked from highest to lowest similarity."
    args_schema: Type[BaseModel] = DomainSemanticSimilarityInput
    _model: Any = None
    
    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self._model = None
        
    def _load_model(self):
        if self._model is None:
            self._model = SentenceTransformer('all-MiniLM-L6-v2')
        return self._model
    
    def _run(self, json_file_path: str = "all_domains.json") -> str:
        try:
            json_file_path = clean_path(json_file_path)
            app_name = APP_CONFIG["app_name"]
            
            # Try different possible paths to find the file
            possible_paths = [
                json_file_path,
                os.path.join(WORKING_DIR, json_file_path),
                os.path.join(WORKING_DIR, "output", app_name, APP_CONFIG["model_name"], "domains", json_file_path),
                os.path.join(WORKING_DIR, "output", json_file_path)
            ]
            
            file_path = None
            for path in possible_paths:
                if os.path.exists(path):
                    file_path = path
                    break
                    
            if not file_path:
                return f"Error: Could not find domain file at any of these locations: {possible_paths}"
                
            with open(file_path, 'r', encoding='utf-8') as f:
                domains_data = json.load(f)
            
            # Extract domain names and their content
            domain_texts = {}
            
            # Handle different possible JSON structures
            if isinstance(domains_data, dict) and "business_domains" in domains_data:
                # Format from domain_clusters.json
                for domain in domains_data["business_domains"]:
                    domain_name = domain["domain_name"]
                    domain_texts[domain_name] = domain["description"]
            elif isinstance(domains_data, dict):
                # Format from all_domains.json with domain names as keys
                for domain_name, classes in domains_data.items():
                    if isinstance(classes, list):
                        domain_texts[domain_name] = " ".join(classes)
                    else:
                        domain_texts[domain_name] = str(classes)
            else:
                return f"Error: Unsupported JSON format in {file_path}"
                
            if len(domain_texts) < 2:
                return f"Error: Found only {len(domain_texts)} domains. Need at least 2 domains to calculate similarity."
                
            # Load model and calculate embeddings
            model = self._load_model()
            domain_names = list(domain_texts.keys())
            domain_texts_list = list(domain_texts.values())
            
            # Calculate embeddings
            embeddings = model.encode(domain_texts_list)
            
            # Calculate pairwise similarities
            similarities = []
            for i in range(len(domain_names)):
                for j in range(i + 1, len(domain_names)):
                    similarity = cosine_similarity([embeddings[i]], [embeddings[j]])[0][0]
                    similarities.append({
                        "domain1": domain_names[i],
                        "domain2": domain_names[j],
                        "similarity": float(similarity)
                    })
            
            # Sort by similarity score (highest first)
            similarities.sort(key=lambda x: x["similarity"], reverse=True)
            
            # Format the results
            result = ["Domain Semantic Similarity Ranking:"]
            for i, item in enumerate(similarities, 1):
                result.append(f"{i}. {item['domain1']} ↔ {item['domain2']}: {item['similarity']:.4f}")
                
            return "\n".join(result)
            
        except Exception as e:
            return f"Error calculating domain semantic similarity: {str(e)}"


class CodeSemanticSimilarityInput(BaseModel):
    json_file_path: str = Field(default="",
                                description="Path to the JSON file containing domain data. Default is output/{app_name}/domains/all_domains.json.")
    output_json: bool = Field(default=False,
                              description="Whether to save the results to a JSON file.")
    output_path: str = Field(default="code_similarity_results.json",
                             description="Path to save the JSON results to if output_json is True.")

class CodeSemanticSimilarity(BaseTool):
    name: str = "code_semantic_similarity"
    description: str = "Calculate semantic similarity between code in different domains by analyzing the actual source code of classes in each domain."
    args_schema: Type[BaseModel] = CodeSemanticSimilarityInput
    _model: Any = None
    
    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self._model = None
        
    def _load_model(self):
        if self._model is None:
            # Use a code-specific model instead of a general text model
            # Microsoft's CodeBERT is specifically trained for programming language understanding
            try:
                self._model = SentenceTransformer('microsoft/codebert-base')
            except Exception:
                # Fall back to a general model if CodeBERT is not available
                print("Warning: CodeBERT model not available, falling back to general text model")
                self._model = SentenceTransformer('all-MiniLM-L6-v2')
        return self._model
    
    def _calculate_code_similarity(self, code1, code2):
        """
        Calculate three types of similarity between two code snippets:
        1. Token-based similarity using TF-IDF
        2. Semantic similarity using the code model
        3. Structure similarity using sequence matching
        Returns a tuple of (token_similarity, semantic_similarity, structure_similarity)
        """
        # Ensure we have strings
        if not isinstance(code1, str) or not isinstance(code2, str):
            return (0.0, 0.0, 0.0)
            
        # If either code is empty, return zeros
        if not code1.strip() or not code2.strip():
            return (0.0, 0.0, 0.0)
            
        try:
            # 1. Token-based similarity using TF-IDF
            vectorizer = TfidfVectorizer(
                analyzer='word',
                token_pattern=r'[a-zA-Z_][a-zA-Z0-9_]*|\S+',  # Capture code tokens and symbols
                lowercase=True,
                max_features=5000
            )
            
            # Fit and transform the code snippets
            try:
                tfidf_matrix = vectorizer.fit_transform([code1, code2])
                token_similarity = cosine_similarity(tfidf_matrix[0:1], tfidf_matrix[1:2])[0][0]
            except Exception:
                # If TF-IDF fails (e.g., empty matrix), use a fallback
                token_similarity = 0.0
            
            # 2. Semantic similarity using the code model
            model = self._load_model()
            embeddings = model.encode([code1, code2])
            semantic_similarity = cosine_similarity([embeddings[0]], [embeddings[1]])[0][0]
            
            # 3. Structure similarity using sequence matching
            # Split code into lines and calculate similarity
            code1_lines = code1.splitlines()
            code2_lines = code2.splitlines()
            
            # Use difflib's SequenceMatcher for structural similarity
            matcher = difflib.SequenceMatcher(None, code1_lines, code2_lines)
            structure_similarity = matcher.ratio()
            
            return (float(token_similarity), float(semantic_similarity), float(structure_similarity))
            
        except Exception as e:
            print(f"Error calculating code similarity: {str(e)}")
            # Fall back to basic token similarity if the approach fails
            try:
                # Simple token overlap
                tokens1 = set(re.findall(r'[a-zA-Z_][a-zA-Z0-9_]*', code1))
                tokens2 = set(re.findall(r'[a-zA-Z_][a-zA-Z0-9_]*', code2))
                
                if not tokens1 or not tokens2:
                    return (0.0, 0.0, 0.0)
                    
                # Jaccard similarity as token similarity
                token_sim = len(tokens1.intersection(tokens2)) / len(tokens1.union(tokens2))
                return (token_sim, token_sim, 0.0)  # Use token similarity as a fallback for semantic similarity too
            except:
                return (0.0, 0.0, 0.0)

    def _run(self, json_file_path: str = "", output_json: bool = False, output_path: str = "code_similarity_results.json") -> str:
        try:
            app_name = APP_CONFIG["app_name"]
            
            # If json_file_path is empty, use the default path
            if not json_file_path:
                json_file_path = f"output/{app_name}/{APP_CONFIG['model_name']}/domains/all_domains.json"
                
            # Clean the path and make it absolute if it's not already
            json_file_path = clean_path(json_file_path)
            if not os.path.isabs(json_file_path):
                json_file_path = os.path.join(WORKING_DIR, json_file_path)
                    
            if not os.path.exists(json_file_path):
                return f"Error: Domain file not found at {json_file_path}"
                
            with open(json_file_path, 'r', encoding='utf-8') as f:
                domains_data = json.load(f)
            
            if not isinstance(domains_data, dict):
                return f"Error: Unsupported JSON format in {json_file_path}. Expected a dictionary mapping domain names to class lists."
                
            # Load source code for each domain
            domain_code = {}
            domain_class_code = {}  # Store code for each class in each domain
            
            for domain_name, class_list in domains_data.items():
                if not isinstance(class_list, list):
                    continue
                    
                domain_source_code = []
                domain_class_code[domain_name] = {}
                
                for class_name in class_list:
                    # Try to find the source code file
                    source_code = self._get_class_source_code(class_name, app_name)
                    if source_code:
                        domain_source_code.append(source_code)
                        domain_class_code[domain_name][class_name] = source_code
                
                if domain_source_code:
                    # Join all source code for this domain
                    domain_code[domain_name] = "\n".join(domain_source_code)
            
            if len(domain_code) < 2:
                return f"Error: Found source code for fewer than 2 domains. Need at least 2 domains to calculate similarity."
            
            # Calculate domain-level similarities using all three approaches
            domain_names = list(domain_code.keys())
            domain_similarities = []
            
            for i in range(len(domain_names)):
                for j in range(i + 1, len(domain_names)):
                    domain1 = domain_names[i]
                    domain2 = domain_names[j]
                    
                    # Calculate all three similarity types
                    token_sim, semantic_sim, structure_sim = self._calculate_code_similarity(
                        domain_code[domain1],
                        domain_code[domain2]
                    )
                    
                    domain_similarities.append({
                        "domain1": domain1,
                        "domain2": domain2,
                        "token_similarity": float(token_sim),
                        "semantic_similarity": float(semantic_sim),
                        "structure_similarity": float(structure_sim)
                    })
            
            # Sort by semantic similarity (highest first)
            domain_similarities.sort(key=lambda x: x["semantic_similarity"], reverse=True)
            
            # Calculate class-level similarities
            class_similarities = []
            
            for i, domain1 in enumerate(domain_names):
                for j in range(i + 1, len(domain_names)):
                    domain2 = domain_names[j]
                    
                    # Get all classes in both domains
                    classes_domain1 = list(domain_class_code[domain1].keys())
                    classes_domain2 = list(domain_class_code[domain2].keys())
                    
                    # Skip if either domain has no classes with source code
                    if not classes_domain1 or not classes_domain2:
                        continue
                    
                    # Calculate similarity between each pair of classes
                    pair_similarities = []
                    for class1 in classes_domain1:
                        for class2 in classes_domain2:
                            code1 = domain_class_code[domain1][class1]
                            code2 = domain_class_code[domain2][class2]
                            
                            # Calculate all three similarity types
                            token_sim, semantic_sim, structure_sim = self._calculate_code_similarity(code1, code2)
                            
                            pair_similarities.append({
                                "class1": class1,
                                "class2": class2,
                                "token_similarity": float(token_sim),
                                "semantic_similarity": float(semantic_sim),
                                "structure_similarity": float(structure_sim)
                            })
                    
                    # Sort class pairs by semantic similarity
                    pair_similarities.sort(key=lambda x: x["semantic_similarity"], reverse=True)
                    
                    # Take top 5 most similar class pairs
                    top_pairs = pair_similarities[:5] if len(pair_similarities) > 5 else pair_similarities
                    
                    # Calculate average semantic similarity
                    avg_semantic_sim = sum(p["semantic_similarity"] for p in pair_similarities) / len(pair_similarities) if pair_similarities else 0
                    
                    class_similarities.append({
                        "domain1": domain1,
                        "domain2": domain2,
                        "top_similar_classes": top_pairs,
                        "avg_semantic_similarity": avg_semantic_sim
                    })
            
            # Prepare results for JSON output if needed
            results_data = {
                "domain_similarities": domain_similarities,
                "class_similarities": class_similarities
            }
            
            # Save to JSON file if requested
            if output_json:
                output_path = clean_path(output_path)
                if not os.path.isabs(output_path):
                    output_path = os.path.join(WORKING_DIR, output_path)
                
                try:
                    with open(output_path, 'w', encoding='utf-8') as f:
                        json.dump(results_data, f, indent=2)
                except Exception as e:
                    return f"Error saving results to JSON file: {str(e)}"
            
            # Format the results for display
            result = ["Code Similarity Analysis (All Metrics):"]
            result.append("\n== Domain-Level Similarity Ranking (by Semantic Similarity) ==")
            for i, item in enumerate(domain_similarities, 1):
                result.append(f"{i}. {item['domain1']} ↔ {item['domain2']}:")
                result.append(f"   - Token Similarity: {item['token_similarity']:.4f}")
                result.append(f"   - Semantic Similarity: {item['semantic_similarity']:.4f}")
                result.append(f"   - Structure Similarity: {item['structure_similarity']:.4f}")
            
            result.append("\n== Class-Level Similarity Details ==")
            for domain_pair in class_similarities:
                result.append(f"\n{domain_pair['domain1']} ↔ {domain_pair['domain2']} (Avg Semantic Similarity: {domain_pair['avg_semantic_similarity']:.4f}):")
                for i, pair in enumerate(domain_pair['top_similar_classes'], 1):
                    result.append(f"  {i}. {pair['class1']} ↔ {pair['class2']}:")
                    result.append(f"     - Token Similarity: {pair['token_similarity']:.4f}")
                    result.append(f"     - Semantic Similarity: {pair['semantic_similarity']:.4f}")
                    result.append(f"     - Structure Similarity: {pair['structure_similarity']:.4f}")
            
            if output_json:
                result.append(f"\nResults saved to JSON file: {output_path}")
                
            return "\n".join(result)
            
        except Exception as e:
            return f"Error calculating code semantic similarity: {str(e)}"
    
    def _get_class_source_code(self, class_name: str, app_name: str) -> str:
        """Find and load the source code for a given class directly from resources directory."""
        try:
            # Get java_paths from config
            java_paths = APP_CONFIG.get("java_paths", ["src/main/java"])
            
            # Convert package.name.ClassName to package/name/ClassName.java
            if not class_name or '.' not in class_name:
                print(f"Invalid class name format: {class_name}")
                return ""
                
            package_parts = class_name.split('.')
            class_file = package_parts[-1] + ".java"
            package_path = "/".join(package_parts[:-1])
            
            # Try each java_path in the config
            for java_path in java_paths:
                # Construct the full path to the source file
                resource_path = os.path.join(WORKING_DIR, "resources", app_name, java_path, package_path, class_file)
                
                if os.path.exists(resource_path) and os.path.isfile(resource_path):
                    with open(resource_path, 'r', encoding='utf-8', errors='replace') as f:
                        return f.read()
            
            # If not found in the primary java_paths, try a few common alternatives
            alternative_paths = [
                os.path.join(WORKING_DIR, "resources", app_name, "src", package_path, class_file),
                os.path.join(WORKING_DIR, "resources", app_name, package_path, class_file)
            ]
            
            for path in alternative_paths:
                if os.path.exists(path) and os.path.isfile(path):
                    with open(path, 'r', encoding='utf-8', errors='replace') as f:
                        return f.read()
            
            print(f"Could not find source code for class {class_name}")
            return ""
            
        except Exception as e:
            print(f"Error getting source code for {class_name}: {str(e)}")
            return ""


class AssignCommonClassListInput(BaseModel):
    common_class_domains: dict = Field(..., 
                                      description="A dictionary where keys are common class names and values are objects with 'domains' (list of domains) and 'relationship_type' ('incoming' for utility classes, 'outgoing' for coordinator classes). Example: {'org.example.Util': {'domains': ['domain1'], 'relationship_type': 'incoming'}}. If relationship_type is not specified, it defaults to 'incoming'.")


class AssignCommonClassList(BaseTool):
    name: str = "assign_common_class_list"
    description: str = "Takes a dict of common classes with their domain assignments and relationship types, and ensures proper domain assignments based on dependencies. Handles both incoming dependencies (utility classes) and outgoing dependencies (coordinator classes) simultaneously. Domain assignments propagate according to each class's specified relationship type."
    args_schema: Type[BaseModel] = AssignCommonClassListInput
    _class_info: dict = None
    _inverted_deps: dict = None

    def _load_dependencies(self, app_name):
        """Loads the class_info_dependency.json file."""
        if self._class_info is None:
            context_dir = os.path.join(WORKING_DIR, "context", app_name)
            class_info_file = os.path.join(context_dir, "class_info_dependency.json")
            if not os.path.exists(class_info_file):
                raise FileNotFoundError(f"Class info file not found at {class_info_file}")
            
            with open(class_info_file, 'r', encoding='utf-8') as f:
                self._class_info = json.load(f)

            # Build inverted dependency index
            self._inverted_deps = defaultdict(set)
            for source_class, data in self._class_info.items():
                if "relationships" in data:
                    for rel_type, targets in data["relationships"].items():
                        # Skip relationship types that are not in our valid list
                        if rel_type.upper() not in VALID_RELATIONSHIP_TYPES and not any(rel_type.upper().endswith(vrt) for vrt in VALID_RELATIONSHIP_TYPES):
                            continue
                            
                        # Handle both list and dict formats of targets
                        if isinstance(targets, list):
                            for target in targets:
                                self._inverted_deps[target].add(source_class)
                        elif isinstance(targets, dict):
                            for target in targets.keys():
                                self._inverted_deps[target].add(source_class)

    def _build_dependency_graphs(self, common_classes_by_type):
        """
        Builds dependency graphs for both incoming and outgoing relationships.
        
        Args:
            common_classes_by_type: Dict with keys 'incoming' and 'outgoing', each containing a list of class names
            
        Returns:
            Tuple of (incoming_graph, outgoing_graph)
        """
        # Initialize the graphs
        incoming_graph = defaultdict(set)
        outgoing_graph = defaultdict(set)
        
        all_common_classes = set(common_classes_by_type.get('incoming', [])) | set(common_classes_by_type.get('outgoing', []))
        
        # Build incoming graph (A depends on B)
        for class_name in common_classes_by_type.get('incoming', []):
            if class_name not in self._class_info:
                print(f"Warning: Class {class_name} not found in class_info_dependency.json")
                continue
                
            # Get the relationships (dependencies) of this class
            relationships = self._class_info[class_name].get("relationships", {})
            
            # For each relationship type and target
            for rel_type, targets in relationships.items():
                # Skip relationship types that are not in our valid list
                if rel_type.upper() not in VALID_RELATIONSHIP_TYPES and not any(rel_type.upper().endswith(vrt) for vrt in VALID_RELATIONSHIP_TYPES):
                    continue
                    
                # Handle both list and dict formats of targets
                if isinstance(targets, list):
                    for target in targets:
                        # If the target is also a common class, add it to the graph
                        if target in all_common_classes:
                            # The edge direction is: class_name depends on target
                            incoming_graph[class_name].add(target)
                elif isinstance(targets, dict):
                    for target in targets.keys():
                        if target in all_common_classes:
                            incoming_graph[class_name].add(target)
        
        # Build outgoing graph (A is depended on by B)
        for class_name in common_classes_by_type.get('outgoing', []):
            # For each common class, find other common classes that depend on it
            for other_class in all_common_classes:
                if other_class == class_name:
                    continue
                    
                if other_class not in self._class_info:
                    continue
                    
                # Check if other_class depends on class_name
                relationships = self._class_info[other_class].get("relationships", {})
                for rel_type, targets in relationships.items():
                    # Skip relationship types that are not in our valid list
                    if rel_type.upper() not in VALID_RELATIONSHIP_TYPES and not any(rel_type.upper().endswith(vrt) for vrt in VALID_RELATIONSHIP_TYPES):
                        continue
                        
                    # Handle both list and dict formats of targets
                    if isinstance(targets, list) and class_name in targets:
                        # The edge direction is: class_name is depended on by other_class
                        outgoing_graph[class_name].add(other_class)
                    elif isinstance(targets, dict) and class_name in targets.keys():
                        outgoing_graph[class_name].add(other_class)
        
        return incoming_graph, outgoing_graph

    def _topological_sort(self, graph):
        """Performs topological sorting on the dependency graph."""
        # Create a copy of the graph for processing
        in_degree = {node: 0 for node in graph}
        
        # Calculate in-degree for each node
        for node in graph:
            for neighbor in graph[node]:
                in_degree[neighbor] = in_degree.get(neighbor, 0) + 1
        
        # Start with nodes that have no dependencies (in-degree = 0)
        queue = [node for node, degree in in_degree.items() if degree == 0]
        result = []
        
        # Process the queue
        while queue:
            current = queue.pop(0)
            result.append(current)
            
            # Reduce in-degree of neighbors
            for neighbor in graph.get(current, set()):
                in_degree[neighbor] -= 1
                if in_degree[neighbor] == 0:
                    queue.append(neighbor)
        
        # Check for cycles
        if len(result) != len(graph):
            print("Warning: Cycle detected in dependency graph, topological sort may be incomplete")
        
        return result

    def _run(self, common_class_domains: dict) -> str:
        try:
            app_name = APP_CONFIG["app_name"]
            self._load_dependencies(app_name)
            
            # Process input to extract domains and relationship types
            normalized_input = {}
            common_classes_by_type = {'incoming': [], 'outgoing': []}
            
            for class_name, info in common_class_domains.items():
                # Handle different input formats
                if isinstance(info, list):
                    # Legacy format: just a list of domains with default relationship type
                    domains = info
                    relationship_type = 'incoming'
                elif isinstance(info, dict):
                    # New format: dict with domains and relationship_type
                    domains = info.get('domains', [])
                    relationship_type = info.get('relationship_type', 'incoming')
                    if relationship_type not in ['incoming', 'outgoing']:
                        relationship_type = 'incoming'  # Default to incoming if invalid
                else:
                    # Invalid format, use defaults
                    domains = []
                    relationship_type = 'incoming'
                
                # Store normalized data
                normalized_input[class_name] = {
                    'domains': domains,
                    'relationship_type': relationship_type
                }
                
                # Group classes by relationship type
                common_classes_by_type[relationship_type].append(class_name)
            
            # Build dependency graphs for both relationship types
            incoming_graph, outgoing_graph = self._build_dependency_graphs(common_classes_by_type)
            
            # Perform topological sorts
            incoming_sorted = self._topological_sort(incoming_graph)
            outgoing_sorted = self._topological_sort(outgoing_graph)
            
            # Add any missing classes
            all_classes = set(normalized_input.keys())
            for class_name in all_classes:
                if class_name not in incoming_sorted and normalized_input[class_name]['relationship_type'] == 'incoming':
                    incoming_sorted.append(class_name)
                if class_name not in outgoing_sorted and normalized_input[class_name]['relationship_type'] == 'outgoing':
                    outgoing_sorted.append(class_name)
            
            # Create reversed graphs
            incoming_reversed = defaultdict(set)
            for node, neighbors in incoming_graph.items():
                for neighbor in neighbors:
                    incoming_reversed[neighbor].add(node)
                    
            outgoing_reversed = defaultdict(set)
            for node, neighbors in outgoing_graph.items():
                for neighbor in neighbors:
                    outgoing_reversed[neighbor].add(node)
            
            # Create a copy of the input dictionary to update
            updated_assignments = {k: list(v['domains']) for k, v in normalized_input.items()}
            
            # Process incoming relationships (propagate domains from dependents to dependencies)
            for class_name in incoming_sorted:
                if normalized_input[class_name]['relationship_type'] != 'incoming':
                    continue
                    
                # Get current domain assignments for this class
                current_domains = set(updated_assignments.get(class_name, []))
                
                # Find all classes that depend on this class
                dependent_classes = incoming_reversed.get(class_name, set())
                
                # For each dependent class, ensure this class is assigned to all domains
                # where the dependent class is assigned
                for dependent in dependent_classes:
                    if normalized_input.get(dependent, {}).get('relationship_type') == 'incoming':
                        dependent_domains = set(updated_assignments.get(dependent, []))
                        # Add all domains from dependent classes to this class
                        current_domains.update(dependent_domains)
                
                # Update the assignments
                updated_assignments[class_name] = list(current_domains)
            
            # Process outgoing relationships (propagate domains from dependencies to dependents)
            for class_name in outgoing_sorted:
                if normalized_input[class_name]['relationship_type'] != 'outgoing':
                    continue
                    
                # Get current domain assignments for this class
                current_domains = set(updated_assignments.get(class_name, []))
                
                # Find all classes that this class depends on
                dependent_classes = outgoing_reversed.get(class_name, set())
                
                # For each dependent class, ensure this class is assigned to all domains
                # where the dependent class is assigned
                for dependent in dependent_classes:
                    if normalized_input.get(dependent, {}).get('relationship_type') == 'outgoing':
                        dependent_domains = set(updated_assignments.get(dependent, []))
                        # Add all domains from dependent classes to this class
                        current_domains.update(dependent_domains)
                
                # Update the assignments
                updated_assignments[class_name] = list(current_domains)
            
            # Format the result
            result = {
                "original_assignments": {
                    k: {'domains': v['domains'], 'relationship_type': v['relationship_type']} 
                    for k, v in normalized_input.items()
                },
                "updated_assignments": {
                    k: updated_assignments[k] for k in normalized_input.keys()
                },
                "dependency_graphs": {
                    "incoming": {k: "depends on " + ", ".join(list(v)) for k, v in incoming_graph.items() if v},
                    "outgoing": {k: "is depended on by " + ", ".join(list(v)) for k, v in outgoing_graph.items() if v}
                }
            }
            
            return json.dumps(result, indent=2)
            
        except Exception as e:
            return f"Error in AssignCommonClassList: {str(e)}"


class GetMorePotentialCommonClassesInput(BaseModel):
    common_classes: List[str] = Field(..., 
                                     description="A list of potential common class names to find dependents/dependencies for.")


class GetMorePotentialCommonClasses(BaseTool):
    name: str = "get_more_potential_common_classes"
    description: str = "Takes a list of potential common classes and returns all their dependents and dependencies that could be additional potential common classes. This helps identify classes that might need to be included in the common class list."
    args_schema: Type[BaseModel] = GetMorePotentialCommonClassesInput
    _class_info: dict = None

    def _load_dependencies(self, app_name):
        """Loads the class_info_dependency.json file."""
        if self._class_info is None:
            context_dir = os.path.join(WORKING_DIR, "context", app_name)
            class_info_file = os.path.join(context_dir, "class_info_dependency.json")
            if not os.path.exists(class_info_file):
                raise FileNotFoundError(f"Class info file not found at {class_info_file}")
            
            with open(class_info_file, 'r', encoding='utf-8') as f:
                self._class_info = json.load(f)

    def _run(self, common_classes: List[str]) -> str:
        try:
            app_name = APP_CONFIG["app_name"]
            self._load_dependencies(app_name)
            
            # Initialize results
            related_classes = defaultdict(set)  # Classes directly depended on by common classes
            # all_classes = set()  # All classes in the system
            # non_common_dependents = set()  # Classes that depend on common classes but aren't common classes
            
            # Build dependency maps
            for class_name, class_data in self._class_info.items():
                # all_classes.add(class_name)
                
                # Only process classes that are in the common_classes list
                if class_name not in common_classes:
                    continue
                
                relationships = class_data.get("relationships", {})
                
                # For each relationship type and target
                for rel_type, targets in relationships.items():
                    # Skip relationship types that are not in our valid list
                    if rel_type.upper() not in VALID_RELATIONSHIP_TYPES and not any(rel_type.upper().endswith(vrt) for vrt in VALID_RELATIONSHIP_TYPES):
                        if rel_type.upper() not in VALID_INVERTED_RELATIONSHIP_TYPES and not any(rel_type.upper().endswith(vrt) for vrt in VALID_INVERTED_RELATIONSHIP_TYPES):
                            continue
                        else:
                            # Handle both list and dict formats of targets
                            if isinstance(targets, list):
                                for target in targets:
                                    related_classes[class_name].add(target)
                            elif isinstance(targets, dict):
                                for target in targets.keys():
                                    related_classes[class_name].add(target)

                    else:
                        # Handle both list and dict formats of targets
                        if isinstance(targets, list):
                            for target in targets:
                                related_classes[class_name].add(target)
                        elif isinstance(targets, dict):
                            for target in targets.keys():
                                related_classes[class_name].add(target)
            
            # Find classes that are depended on by common classes
            relate_set = set()
            for deps in related_classes.values():
                relate_set.update(deps)
            
            # Filter out classes that are already in common_classes
            potential_common_classes = relate_set.difference(set(common_classes))
            
            # Format the result
            result = {
                "input_common_classes": common_classes,
                "more_potential_common_classes": list(potential_common_classes),
                "note": "These potential common classes are the dependents or dependencies of your given common classes, which are POSSIBLE common classes you fail to identify. You should check their code and dependency to further decide whether they are common classes (e.g.utility/coordinator)."
            }
            
            return json.dumps(result, indent=2)
            
        except Exception as e:
            return f"Error in GetCommonClassDependents: {str(e)}"


class WriteResultToJsonInput(BaseModel):
    domain_name: str = Field(..., description="The name of the domain to write results for.")
    class_list: List[str] = Field(..., description="List of fully qualified class names belonging to this domain.")


class WriteResultToJson(BaseTool):
    """
    Tool for LLM to write domain results one at a time.
    This avoids output token limit issues when dealing with many domains.
    The LLM should call this tool once for each domain.
    """
    name: str = "write_result_to_json"
    description: str = """Write the class assignment result for a single domain. 
    Call this tool ONCE for EACH domain to save its assigned classes. 
    This allows you to output results incrementally without hitting token limits.
    After calling this for all domains, the results will be automatically merged."""
    args_schema: Type[BaseModel] = WriteResultToJsonInput
    
    # Class variable to accumulate results across multiple calls
    _accumulated_results: dict = {}
    _output_file: str = None
    
    @classmethod
    def reset(cls):
        """Reset accumulated results for a new task run."""
        cls._accumulated_results = {}
        cls._output_file = None
    
    @classmethod
    def set_output_file(cls, output_file: str):
        """Set the output file path for saving results."""
        cls._output_file = output_file
        # Ensure directory exists
        os.makedirs(os.path.dirname(output_file), exist_ok=True)
    
    @classmethod
    def get_accumulated_results(cls) -> dict:
        """Get all accumulated results."""
        return cls._accumulated_results.copy()
    
    def _run(self, domain_name: str, class_list: List[str]) -> str:
        """
        Write the result for a single domain.
        
        Args:
            domain_name: The name of the domain
            class_list: List of class names belonging to this domain
            
        Returns:
            Confirmation message
        """
        try:
            # Accumulate the result
            WriteResultToJson._accumulated_results[domain_name] = class_list
            
            # Also write to file incrementally if output file is set
            if WriteResultToJson._output_file:
                with open(WriteResultToJson._output_file, 'w', encoding='utf-8') as f:
                    json.dump(WriteResultToJson._accumulated_results, f, indent=2)
            
            return f"Successfully saved {len(class_list)} classes for domain '{domain_name}'. Total domains saved so far: {len(WriteResultToJson._accumulated_results)}"
            
        except Exception as e:
            return f"Error writing domain result: {str(e)}"


class Tools:
    def __init__(self):
        self.tools = [
            # GetSourceCodeTree(),
            GetAllClassHierarchy(),
            GetAllClassHierarchyComplete(),
            GetDatabaseSummary(),
            GetAllClassSummaries(),
            GetClassBasicInfo(),
            GetClassRelationship(),
            GetClassRelationAndCode(),
            GetMultiClassRelationAndCode(),
            GetClassSummary(),
            GetSourceCode(),
            ListDirectory(),
            SearchDirectory(),
            SearchClassInfo(),
            SearchFile(),
            GetRelatedClassList(),
            RankDependencyEntropyAndRatio(),
            CodebaseSemanticSearch(),
            AnalyzeDomainRelationMetrics(),
            DomainSemanticSimilarity(),
            CodeSemanticSimilarity(),
            AssignCommonClassList(),
            GetMorePotentialCommonClasses(),
            WriteResultToJson(),
            # AnalyzeDomainCohesion(),
            # GetClassDependency(),
            # GetFileInfo(),
            AnalyzeData()
        ]

    def get_tools(self):
        return self.tools

