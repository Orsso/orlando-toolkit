import pytest
from orlando_toolkit.core.utils import clean_heading_text


class TestCleanHeadingText:
    """Test cases for clean_heading_text function."""

    def test_decimal_numbering_with_dots(self):
        """Test removal of decimal numbering patterns with dots."""
        assert clean_heading_text("1.2.3 My Title") == "My Title"
        assert clean_heading_text("1.2.3. My Title") == "My Title"
        assert clean_heading_text("1.2 Introduction") == "Introduction"
        assert clean_heading_text("1 Chapter One") == "Chapter One"

    def test_decimal_numbering_with_parenthesis(self):
        """Test removal of decimal numbering with parenthesis."""
        assert clean_heading_text("1) My Title") == "My Title"
        assert clean_heading_text("10) My Title") == "My Title"
        assert clean_heading_text("123) My Title") == "My Title"

    def test_decimal_numbering_with_dash(self):
        """Test removal of decimal numbering with dash."""
        assert clean_heading_text("1- My Title") == "My Title"
        assert clean_heading_text("10- My Title") == "My Title"

    def test_letter_numbering_with_parenthesis(self):
        """Test removal of letter numbering with parenthesis."""
        assert clean_heading_text("a) My Title") == "My Title"
        assert clean_heading_text("A) My Title") == "My Title"
        assert clean_heading_text("z) My Title") == "My Title"
        assert clean_heading_text("Z) My Title") == "My Title"

    def test_letter_numbering_with_dash(self):
        """Test removal of letter numbering with dash."""
        assert clean_heading_text("a- My Title") == "My Title"
        assert clean_heading_text("A- My Title") == "My Title"

    def test_roman_numerals_with_period(self):
        """Test removal of Roman numeral patterns."""
        # Lowercase Roman numerals
        assert clean_heading_text("i. My Title") == "My Title"
        assert clean_heading_text("ii. My Title") == "My Title"
        assert clean_heading_text("iv. My Title") == "My Title"
        assert clean_heading_text("ix. My Title") == "My Title"
        assert clean_heading_text("xiv. My Title") == "My Title"

        # Uppercase Roman numerals  
        assert clean_heading_text("I. My Title") == "My Title"
        assert clean_heading_text("II. My Title") == "My Title"
        assert clean_heading_text("IV. My Title") == "My Title"
        assert clean_heading_text("IX. My Title") == "My Title"
        assert clean_heading_text("XIV. My Title") == "My Title"

    def test_titles_without_numbering(self):
        """Test that titles without numbering remain unchanged."""
        assert clean_heading_text("My Title") == "My Title"
        assert clean_heading_text("Introduction") == "Introduction"
        assert clean_heading_text("Chapter One") == "Chapter One"
        assert clean_heading_text("Conclusion and Future Work") == "Conclusion and Future Work"

    def test_numbering_in_middle_not_removed(self):
        """Test that numbering in the middle of titles is preserved."""
        assert clean_heading_text("Version 1.2.3 Notes") == "Version 1.2.3 Notes"
        assert clean_heading_text("My Title (Part 1)") == "My Title (Part 1)"
        assert clean_heading_text("Section A: Introduction") == "Section A: Introduction"

    def test_complex_titles_with_special_characters(self):
        """Test titles with special characters and formatting."""
        assert clean_heading_text("1.2.3 Installation & Configuration") == "Installation & Configuration"
        assert clean_heading_text("1) FAQ - Frequently Asked Questions") == "FAQ - Frequently Asked Questions"
        assert clean_heading_text("I. À propos de ce document") == "À propos de ce document"

    def test_edge_cases(self):
        """Test edge cases and boundary conditions."""
        # Empty string
        assert clean_heading_text("") == ""
        
        # None input
        assert clean_heading_text(None) is None
        
        # Non-string input
        assert clean_heading_text(123) == 123
        
        # Only numbering (fallback to original)
        assert clean_heading_text("1.2.3") == "1.2.3"
        assert clean_heading_text("1)") == "1)"
        
        # Whitespace handling
        assert clean_heading_text("1.2.3   My Title   ") == "My Title"
        assert clean_heading_text("  1) My Title") == "My Title"

    def test_multiple_spaces_normalized(self):
        """Test that multiple spaces between numbering and title are handled."""
        assert clean_heading_text("1.2.3     My Title") == "My Title"
        assert clean_heading_text("1)    My Title") == "My Title"
        assert clean_heading_text("I.        My Title") == "My Title"

    def test_preserves_original_casing(self):
        """Test that original casing of the title is preserved."""
        assert clean_heading_text("1.2.3 UPPERCASE TITLE") == "UPPERCASE TITLE"
        assert clean_heading_text("1) lowercase title") == "lowercase title"
        assert clean_heading_text("I. MiXeD CaSe TiTlE") == "MiXeD CaSe TiTlE"