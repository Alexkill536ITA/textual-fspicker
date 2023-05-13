"""Provides a widget for directory navigation."""

##############################################################################
# Python imports.
from __future__        import annotations
from dataclasses       import dataclass
from datetime          import datetime
from pathlib           import Path
from typing            import Iterable
from typing_extensions import Final

##############################################################################
# Rich imports.
from rich.console import RenderableType
from rich.table   import Table
from rich.text    import Text

##############################################################################
# Textual imports.
from textual                     import work
from textual.reactive            import var
from textual.message             import Message
from textual.widgets             import OptionList
from textual.widgets.option_list import Option
from textual.worker              import get_current_worker

##############################################################################
class DirectoryEntry( Option ):
    """A directory entry for the `DirectoryNaviation` class."""

    FOLDER_ICON: Final[ RenderableType ] = Text.from_markup( ":file_folder:" )
    """The icon to use for a folder."""

    def __init__( self, location: Path ) -> None:
        self.location: Path = location.resolve()
        """The location of this directory entry."""
        super().__init__( self._as_renderable( location ) )

    @staticmethod
    def _mtime( location: Path ) -> str:
        """Get a formatted modification time for the given location.

        Args:
            location: The location to get the modification time for.

        Returns:
            The formatted modification time, to the nearest second.
        """
        return datetime.fromtimestamp( int( location.stat().st_mtime ) ).isoformat().replace( "T", " " )

    def _as_renderable( self, location: Path ) -> RenderableType:
        """Create the renderable for this entry.

        Args:
            location: The location to turn into a renderable.

        Returns:
            The entry as a Rich renderable.
        """
        prompt = Table.grid( expand=True )
        prompt.add_column( no_wrap=True, justify="left", width=3 )
        prompt.add_column( no_wrap=True, justify="left", ratio=1 )
        prompt.add_column( no_wrap=True, justify="right", width=20 )
        prompt.add_row(
            self.FOLDER_ICON,
            location.name,
            self._mtime( location )
        )
        return prompt

##############################################################################
class DirectoryNavigation( OptionList ):
    """A directory navigation widget."""

    DEFAULT_CSS = """
    DirectoryNavigation {
        padding-left: 1;
        padding-right: 1;
    }
    """

    @dataclass
    class Changed( Message ):
        """Message sent when the current directory has changed."""

        control: DirectoryNavigation
        """The directory navigation control that changed."""

    _location: var[ Path ] = var[ Path ]( Path( "." ).resolve(), init=False )
    """The current location for the directory."""

    show_hidden: var[ bool ] = var( False )
    """Should hidden entries be shown?"""

    sort_display: var[ bool ] = var( True )
    """Should the display be sorted?"""

    def __init__( self, location: Path | str | None = None ) -> None:
        """Initialise the directory navigation widget.

        Args:
            location: The starting location.
        """
        super().__init__()
        self._mounted                       = False
        self.location                       = Path( "~" if location is None else location ).expanduser().resolve()
        self._entries: list[DirectoryEntry] = []

    @property
    def location( self ) -> Path:
        """The current location of the navigation widget."""
        return self._location

    @location.setter
    def location( self, new_location: Path | str ) -> None:
        new_location = Path( new_location ).expanduser().resolve()
        if self._mounted:
            self._location = new_location
        else:
            self._initial_location = new_location

    def on_mount( self ) -> None:
        """Populate the widget once the DOM is ready."""
        self._mounted = True
        self._location = self._initial_location

    def _settle_highlight( self ) -> None:
        """Settle the highlight somewhere useful if it's not anywhere."""
        if self.highlighted is None:
            self.highlighted = 0

    @property
    def is_root( self ) -> bool:
        """Are we at the root of the filesystem?"""
        # TODO: Worry about portability.
        return self._location == Path( self._location.root )

    @staticmethod
    def is_hidden( path: Path ) -> bool:
        """Does the given path appear to be hidden?

        Args:
            path: The path to test.

        Returns:
            `True` if the path appears to be hidden, `False` if not.

        Note:
            For the moment this simply checks for the 'dot hack'. Eventually
            I'll extend this to detect hidden files in the most appropriate
            way for the current operating system.
        """
        return path.name.startswith( "." )

    def hide( self, path: Path ) -> bool:
        """Should we hide the given path?

        Args:
            path: The path to test.

        Returns:
            `True` if the path should be hidden, `False` if not.
        """
        return self.is_hidden( path ) and not self.show_hidden

    def _sort( self, entries: Iterable[ DirectoryEntry ] ) -> Iterable[ DirectoryEntry ]:
        """Sort the entries as per the value of `sort_display`."""
        if self.sort_display:
            return sorted( entries, key=lambda entry: entry.location.name )
        return entries

    def _repopulate_display( self ) -> None:
        """Repopulate the display of directories."""
        with self.app.batch_update():
            self.clear_options()
            if not self.is_root:
                self.add_option( DirectoryEntry( self._location / ".." ) )
            self.add_options( self._sort( entry for entry in self._entries if not self.hide( entry.location ) ) )
        self._settle_highlight()

    @work(exclusive=True)
    def _load( self ) -> None:
        """Load the current directory data."""

        # Because we might end up slicing and dicing the list, and there's
        # little point in reloading the data from the filesystem again if
        # all the user is doing is requesting hidden files be shown/hidden,
        # or the sort order be changed, or something, we're going to keep a
        # parallel copy of *all* possible options for the list and then
        # populate from that.
        self._entries = []

        # Now loop over the directory, looking for directories within and
        # streaming them into the list via the app thread.
        worker = get_current_worker()
        for entry in self._location.iterdir():
            if entry.is_dir():
                self._entries.append( DirectoryEntry( self._location / entry.name ) )
            if worker.is_cancelled:
                return

        # Now that we've loaded everything up, let's make the call to update
        # the display.
        self.app.call_from_thread( self._repopulate_display )

    def _watch__location( self ) -> None:
        """Reload the content if the location changes."""
        self.post_message( self.Changed( self ) )
        self._load()

    def _watch_show_hidden( self ) -> None:
        """Reload the content if the show-hidden flag has changed."""
        self._repopulate_display()

    def _watch_sort_display( self ) -> None:
        """Refresh the display if the sort option has been changed."""
        self._repopulate_display()

    def toggle_hidden( self ) -> None:
        """Toggle the display of hidden filesystem entries."""
        self.show_hidden = not self.show_hidden

    def _on_option_list_option_selected( self, event: OptionList.OptionSelected ) -> None:
        """Handle an entry in the list being selected.

        Args:
            event: The event to handle.
        """
        event.stop()
        assert isinstance( event.option, DirectoryEntry )
        self._location = event.option.location

### directory_navigation.py ends here
