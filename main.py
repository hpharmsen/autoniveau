from pathlib import Path
import re
import time

from dotenv import load_dotenv
from justai import Translator
from justai.translator.translator import parse_xliff_with_unit_clusters

USE_CACHE = True


def language_code(language):
    languages = {
        "Bulgaars": "bg-BG",
        "Duits": "de-DE",
        "Engels": "en-GB",
        "Frans": "fr-FR",
        "Grieks": "el-GR",
        "Italiaans": "it-IT",
        "Oekraïens": "uk-UA",
        "Pools": "pl-PL",
        "Portugees": "pt-PT",
        "Roemeens": "ro-RO",
        "Russisch": "ru-RU",
        "Spaans": "es-ES"
    }
    return languages.get(language, None)  # Retourneert None als de taal niet gevonden is.


def run_test(input_file: [Path | str], language: str, use_clusters=False):
    if isinstance(input_file, str):
        input_file = Path(input_file)
    tr = Translator()
    if use_clusters:
        with open(input_file, 'r') as f:
            xliff_content = f.read()
        result = parse_xliff_with_unit_clusters(xliff_content, 32768)
        header = result['header']
        clusters = result['units']
        footer = result['footer']
        xliff_version = result['version']
        translated = ''
        for index, cluster in enumerate(clusters):
            #if index != 2:
            #    continue # !!
            tr.read(header + cluster + footer)
            translated_cluster = tr.translate(language, string_cached=USE_CACHE)

            if xliff_version == '2.0':
                xliff_without_header_and_footer_match = re.search(r'<unit[\s\S]*<\/unit>', translated_cluster)
            else:
                xliff_without_header_and_footer_match = re.search(r'<trans-unit[\s\S]*<\/trans-unit>',
                                                                  translated_cluster)

            # Controleer of er een match gevonden is en voeg deze toe aan translated_units
            if xliff_without_header_and_footer_match:
                translated_cluster = xliff_without_header_and_footer_match.group(0)
                translated += translated_cluster

        # In geval van XLIFF 2.0, voeg de target language (trgLang) toe aan de header.
        if xliff_version == "2.0":
            lang_code = language_code(language)
            # Vervang om trgLang="en-GB" of een andere taalcode, zoals nl-NL, in de header te zetten.
            header = re.sub(r'(<xliff [^>]*)(>)', r'\1 trgLang="{}"\2'.format(lang_code), header)

        translated = header + translated + footer
    else:
        try:
            tr.load(input_file)
        except ValueError as e:
            print(e.args[0])
            return
        translated = tr.translate(language)
    outfile = f'{input_file.parent}/{input_file.stem} {language}.xlf'
    with open(outfile, 'w') as f:
        f.write(translated)
    outfile = f'{input_file.parent}/{input_file.stem} {language}.xml'
    with open(outfile, 'w') as f:
        f.write(translated)


INPUTS = {1: 'TR 5234 Diagnose Motormanagement en Aandrijflijn 2023.xlf',
          2: 'AI E2 test document.xlf',
          3: 'AI_2.1.xlf'}


def inp(no: int):
    global INPUTS
    return Path('input') / INPUTS[no]


if __name__ == "__main__":
    load_dotenv()
    start = time.time()

    run_test(inp(2), 'Duits', use_clusters=True)

    print(f'Duration: {time.time() - start:.2f} seconds')
