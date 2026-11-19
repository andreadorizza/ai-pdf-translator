# AGPL-3.0 because of PyMuPDF and PDFMathTranslate

PyMuPDF renders the pages and writes the translation into the PDF, and it is licensed AGPL-3.0 or under a paid Artifex licence. PDFMathTranslate, which does the layout and write-back (see ADR 0003), is AGPL-3.0 too. We publish the whole tool under AGPL-3.0: no other library we found both renders scans and places shaped text into boxes as simply. Moving to MIT later means replacing both.
